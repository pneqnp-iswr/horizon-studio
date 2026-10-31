//! Ownership of the core's process tree (security review S2).
//!
//! The core is told to stop by closing its stdin (EOF), and is killed if it does not stop in time.
//! That covers a responsive core and a hung one while the shell is alive. It does not cover:
//! - the shell itself crashing or being killed, because `Drop` never runs; a hung core would then never see EOF;
//! - processes the core started, such as a Preview Bridge game, which outlive a killed parent.
//!
//! So the shell also owns the core's whole tree:
//! - **Windows:** the core runs in a Job Object with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`. Only the shell holds the
//!   job handle, and Windows closes it when the shell exits for any reason, crashes included. Every process in the
//!   job is then terminated. Child processes join their parent's job automatically. The core starts no process
//!   before its handshake, and it is assigned right after it is spawned, so nothing escapes in between.
//! - **Linux and macOS:** the core leads its own process group, and stopping the core kills the group, so nothing
//!   it started outlives it. If the shell is killed with SIGKILL, a responsive core still stops at EOF. A hung core
//!   is not stopped in that case, because there is no portable kernel equivalent of kill-on-close.
//!   `PR_SET_PDEATHSIG` is not one: it fires when the spawning *thread* exits, and the core is started from a
//!   short-lived boot thread.

use std::process::{Child, Command};

/// How the tree is contained, for the smoke report.
pub fn kind() -> &'static str {
    if cfg!(windows) {
        "job-object"
    } else if cfg!(unix) {
        "process-group"
    } else {
        "none"
    }
}

/// Prepares `command` so that its tree can be owned: on Unix it leads a new process group.
pub fn prepare(command: &mut Command) {
    #[cfg(unix)]
    {
        use std::os::unix::process::CommandExt;
        command.process_group(0);
    }
    #[cfg(not(unix))]
    let _ = command;
}

pub struct Tree {
    #[cfg(windows)]
    job: Option<win::Job>,
    #[cfg(unix)]
    group: Option<i32>,
}

impl Tree {
    /// Takes ownership of `child`'s tree. `contained()` says whether that worked; a shell that
    /// cannot contain its core still runs, and reports it.
    pub fn adopt(child: &Child) -> Tree {
        #[cfg(windows)]
        {
            let job = win::Job::kill_on_close().and_then(|job| job.assign(child).map(|()| job)).ok();
            Tree { job }
        }
        #[cfg(unix)]
        {
            Tree { group: i32::try_from(child.id()).ok().filter(|pid| *pid > 1) }
        }
        #[cfg(not(any(windows, unix)))]
        {
            let _ = child;
            Tree {}
        }
    }

    pub fn contained(&self) -> bool {
        #[cfg(windows)]
        return self.job.is_some();
        #[cfg(unix)]
        return self.group.is_some();
        #[cfg(not(any(windows, unix)))]
        false
    }

    /// Stops every process still in the tree. Safe to call more than once.
    pub fn kill(&mut self) {
        #[cfg(windows)]
        {
            // Closing the only handle terminates every process in the job.
            self.job.take();
        }
        #[cfg(unix)]
        if let Some(group) = self.group.take() {
            // SAFETY: kill(2) with a negative id signals that process group; no memory is involved.
            unsafe {
                libc::kill(-group, libc::SIGKILL);
            }
        }
    }
}

impl Drop for Tree {
    fn drop(&mut self) {
        self.kill();
    }
}

#[cfg(windows)]
mod win {
    use std::os::windows::io::AsRawHandle;
    use std::process::Child;

    use windows_sys::Win32::Foundation::{CloseHandle, HANDLE};
    use windows_sys::Win32::System::JobObjects::{
        AssignProcessToJobObject, CreateJobObjectW, JobObjectExtendedLimitInformation, SetInformationJobObject,
        JOBOBJECT_EXTENDED_LIMIT_INFORMATION, JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
    };

    pub struct Job(HANDLE);

    // SAFETY: a job handle may be used and closed from any thread.
    unsafe impl Send for Job {}
    unsafe impl Sync for Job {}

    impl Job {
        pub fn kill_on_close() -> Result<Job, String> {
            // SAFETY: plain Win32 calls with valid arguments; the handle is owned by the returned Job.
            unsafe {
                let handle = CreateJobObjectW(std::ptr::null(), std::ptr::null());
                if handle.is_null() {
                    return Err(format!("CreateJobObjectW failed: {}", std::io::Error::last_os_error()));
                }
                let job = Job(handle);
                let mut info: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = std::mem::zeroed();
                info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
                let ok = SetInformationJobObject(
                    job.0,
                    JobObjectExtendedLimitInformation,
                    std::ptr::from_ref(&info).cast(),
                    std::mem::size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
                );
                if ok == 0 {
                    return Err(format!("SetInformationJobObject failed: {}", std::io::Error::last_os_error()));
                }
                Ok(job)
            }
        }

        pub fn assign(&self, child: &Child) -> Result<(), String> {
            // SAFETY: both handles are valid for the duration of the call.
            let ok = unsafe { AssignProcessToJobObject(self.0, child.as_raw_handle() as HANDLE) };
            if ok == 0 {
                return Err(format!("AssignProcessToJobObject failed: {}", std::io::Error::last_os_error()));
            }
            Ok(())
        }
    }

    impl Drop for Job {
        fn drop(&mut self) {
            // SAFETY: the handle came from CreateJobObjectW and is closed exactly once.
            unsafe {
                CloseHandle(self.0);
            }
        }
    }
}

#[cfg(test)]
pub mod tests_support {
    use std::time::{Duration, Instant};

    /// Whether process `pid` still runs (a zombie waiting to be reaped counts as gone).
    pub fn alive(pid: u32) -> bool {
        #[cfg(windows)]
        {
            use windows_sys::Win32::Foundation::{CloseHandle, WAIT_TIMEOUT};
            use windows_sys::Win32::System::Threading::{OpenProcess, WaitForSingleObject, PROCESS_SYNCHRONIZE};
            // SAFETY: plain Win32 calls; the handle is closed before returning.
            unsafe {
                let handle = OpenProcess(PROCESS_SYNCHRONIZE, 0, pid);
                if handle.is_null() {
                    return false;
                }
                let running = WaitForSingleObject(handle, 0) == WAIT_TIMEOUT;
                CloseHandle(handle);
                running
            }
        }
        #[cfg(unix)]
        {
            match std::fs::read_to_string(format!("/proc/{pid}/stat")) {
                Ok(stat) => !stat.rsplit(')').next().unwrap_or("").trim_start().starts_with('Z'),
                // No procfs (macOS): signal 0 only checks that the process exists.
                // SAFETY: kill(2) with signal 0 sends nothing.
                Err(_) => unsafe { libc::kill(pid as i32, 0) == 0 },
            }
        }
    }

    pub fn wait_gone(pid: u32) -> bool {
        let started = Instant::now();
        while started.elapsed() < Duration::from_secs(10) {
            if !alive(pid) {
                return true;
            }
            std::thread::sleep(Duration::from_millis(50));
        }
        false
    }
}

#[cfg(test)]
mod tests {
    use super::tests_support::{alive, wait_gone};
    use super::*;
    use std::process::Stdio;
    use std::time::{Duration, Instant};

    fn python() -> String {
        std::env::var("HORIZON_STUDIO_PYTHON").unwrap_or_else(|_| if cfg!(windows) { "python" } else { "python3" }.to_string())
    }

    /// A parent that starts a grandchild, prints its pid and then hangs, ignoring EOF.
    fn family() -> (Child, Tree, u32) {
        let script = "import subprocess, sys, time\n\
            g = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n\
            print(g.pid, flush=True)\n\
            while True:\n    time.sleep(1)\n";
        let mut command = Command::new(python());
        command.args(["-c", script]).stdin(Stdio::null()).stdout(Stdio::piped());
        prepare(&mut command);
        let mut child = command.spawn().expect("python runs");
        let tree = Tree::adopt(&child);
        let mut line = String::new();
        std::io::BufRead::read_line(&mut std::io::BufReader::new(child.stdout.take().unwrap()), &mut line).unwrap();
        let grandchild: u32 = line.trim().parse().expect("grandchild pid");
        assert!(alive(grandchild));
        (child, tree, grandchild)
    }

    #[test]
    fn killing_the_tree_stops_the_core_and_what_it_started() {
        let (mut child, mut tree, grandchild) = family();
        assert!(tree.contained(), "the tree is owned ({})", kind());
        tree.kill();
        let started = Instant::now();
        while child.try_wait().unwrap().is_none() {
            assert!(started.elapsed() < Duration::from_secs(10), "the hung parent was stopped");
            std::thread::sleep(Duration::from_millis(50));
        }
        assert!(wait_gone(grandchild), "the grandchild did not outlive its parent");
    }

    #[test]
    fn dropping_the_owner_stops_the_tree_like_a_crashed_shell_would() {
        // On Windows this is the kill-on-close path the OS also takes when the shell dies.
        let (mut child, tree, grandchild) = family();
        drop(tree);
        assert!(wait_gone(grandchild));
        let _ = child.kill();
        let _ = child.wait();
    }
}
