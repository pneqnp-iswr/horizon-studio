//! The Python project core as a child process (`launcher.py --serve`, protocol
//! `horizon-studio.core/1`). The shell holds the core's stdin; closing it, or the shell
//! dying, makes the core shut down, so no server outlives the window.

use std::fs::File;
use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::mpsc;
use std::thread;
use std::time::{Duration, Instant};

use serde::Deserialize;
use tauri::Url;

pub const PROTOCOL: &str = "horizon-studio.core/1";

#[cfg(windows)]
const CORE_NAME: &str = "horizon-studio-core.exe";
#[cfg(not(windows))]
const CORE_NAME: &str = "horizon-studio-core";

/// How the core is started.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Launch {
    /// The frozen core shipped next to the shell in `core/`.
    Frozen(PathBuf),
    /// Development builds only: the repository's `launcher.py` with a system Python.
    #[cfg_attr(not(debug_assertions), allow(dead_code))]
    Script { python: String, script: PathBuf },
}

impl Launch {
    pub fn kind(&self) -> &'static str {
        match self {
            Launch::Frozen(_) => "frozen",
            Launch::Script { .. } => "script",
        }
    }
}

/// Finds the core: `<dir>/core/horizon-studio-core[.exe]` beside the installed shell.
/// Release builds never fall back to an interpreter found on the system.
pub fn locate(dirs: &[PathBuf]) -> Result<Launch, String> {
    let candidates: Vec<PathBuf> = dirs.iter().map(|dir| dir.join("core").join(CORE_NAME)).collect();
    if let Some(found) = candidates.iter().find(|path| path.is_file()) {
        return Ok(Launch::Frozen(found.clone()));
    }
    #[cfg(debug_assertions)]
    {
        let script = Path::new(env!("CARGO_MANIFEST_DIR")).join("..").join("launcher.py");
        if script.is_file() {
            let python = std::env::var("HORIZON_STUDIO_PYTHON")
                .unwrap_or_else(|_| if cfg!(windows) { "python" } else { "python3" }.to_string());
            return Ok(Launch::Script { python, script });
        }
    }
    let searched: Vec<String> = candidates.iter().map(|p| p.display().to_string()).collect();
    Err(format!("The Horizon Studio core was not found. Searched: {}", searched.join(", ")))
}

#[derive(Debug, Deserialize)]
struct Handshake {
    protocol: String,
    event: String,
    url: String,
    version: String,
    pid: u32,
}

/// Checks the core's first stdout line and returns its loopback URL and version.
pub fn parse_handshake(line: &str) -> Result<(Url, String, u32), String> {
    let handshake: Handshake =
        serde_json::from_str(line.trim()).map_err(|e| format!("Unreadable core handshake ({e}): {}", line.trim()))?;
    if handshake.protocol != PROTOCOL || handshake.event != "ready" {
        return Err(format!("Unexpected core handshake {} / {}", handshake.protocol, handshake.event));
    }
    let url = Url::parse(&handshake.url).map_err(|e| format!("Invalid core URL {}: {e}", handshake.url))?;
    if url.scheme() != "http" || url.host_str() != Some("127.0.0.1") || url.port().is_none() || url.path() != "/" {
        return Err(format!("The core must serve http://127.0.0.1:<port>/, not {url}"));
    }
    Ok((url, handshake.version, handshake.pid))
}

pub struct Core {
    child: Child,
    stdin: Option<ChildStdin>,
    pub url: Url,
    pub version: String,
    pub pid: u32,
    pub launch: Launch,
}

impl Core {
    /// Starts the core and waits for its handshake. Core stderr goes to `log` when given.
    pub fn start(launch: Launch, log: Option<&Path>, timeout: Duration) -> Result<Core, String> {
        let mut command = match &launch {
            Launch::Frozen(path) => Command::new(path),
            Launch::Script { python, script } => {
                let mut command = Command::new(python);
                command.arg(script);
                command
            }
        };
        let stderr = match log.map(File::create) {
            Some(Ok(file)) => Stdio::from(file),
            _ => Stdio::null(),
        };
        command
            .arg("--serve")
            .env("PYTHONUNBUFFERED", "1")
            .env("PYTHONIOENCODING", "utf-8")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(stderr);
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            const CREATE_NO_WINDOW: u32 = 0x0800_0000;
            command.creation_flags(CREATE_NO_WINDOW);
        }
        let mut child = command.spawn().map_err(|e| format!("Could not start the core ({launch:?}): {e}"))?;
        let stdout = child.stdout.take().expect("piped stdout");
        let (sender, receiver) = mpsc::channel();
        thread::spawn(move || {
            let mut reader = BufReader::new(stdout);
            let mut line = String::new();
            let _ = sender.send(reader.read_line(&mut line).map(|_| line));
            // Keep draining so the core never blocks on a full pipe.
            for _ in reader.lines() {}
        });
        let line = match receiver.recv_timeout(timeout) {
            Ok(Ok(line)) if !line.is_empty() => line,
            Ok(Ok(_)) | Ok(Err(_)) => {
                let status = child.wait().ok().and_then(|s| s.code());
                return Err(format!("The core exited before it was ready (exit code {status:?})"));
            }
            Err(_) => {
                let _ = child.kill();
                let _ = child.wait();
                return Err(format!("The core did not report ready within {} s", timeout.as_secs()));
            }
        };
        match parse_handshake(&line) {
            Ok((url, version, pid)) => {
                let stdin = child.stdin.take();
                Ok(Core { child, stdin, url, version, pid, launch })
            }
            Err(error) => {
                let _ = child.kill();
                let _ = child.wait();
                Err(error)
            }
        }
    }

    /// Asks the core to stop by closing its stdin; kills it if it does not exit in time.
    /// Returns the exit code (None when it had to be killed) and how long it took.
    pub fn stop(mut self, timeout: Duration) -> (Option<i32>, bool, Duration) {
        let started = Instant::now();
        drop(self.stdin.take());
        while started.elapsed() < timeout {
            if let Ok(Some(status)) = self.child.try_wait() {
                return (status.code(), false, started.elapsed());
            }
            thread::sleep(Duration::from_millis(25));
        }
        let _ = self.child.kill();
        let code = self.child.wait().ok().and_then(|s| s.code());
        (code, true, started.elapsed())
    }
}

impl Drop for Core {
    fn drop(&mut self) {
        drop(self.stdin.take());
        if let Ok(None) = self.child.try_wait() {
            thread::sleep(Duration::from_millis(200));
            if let Ok(None) = self.child.try_wait() {
                let _ = self.child.kill();
                let _ = self.child.wait();
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn accepts_only_a_loopback_handshake() {
        let ok = r#"{"protocol":"horizon-studio.core/1","event":"ready","url":"http://127.0.0.1:40123/","version":"0.7.0","pid":7}"#;
        let (url, version, pid) = parse_handshake(ok).unwrap();
        assert_eq!((url.port(), version.as_str(), pid), (Some(40123), "0.7.0", 7));
        for bad in [
            r#"{"protocol":"other/1","event":"ready","url":"http://127.0.0.1:1/","version":"x","pid":1}"#,
            r#"{"protocol":"horizon-studio.core/1","event":"stopped","url":"http://127.0.0.1:1/","version":"x","pid":1}"#,
            r#"{"protocol":"horizon-studio.core/1","event":"ready","url":"http://example.com:80/","version":"x","pid":1}"#,
            r#"{"protocol":"horizon-studio.core/1","event":"ready","url":"https://127.0.0.1:1/","version":"x","pid":1}"#,
            r#"{"protocol":"horizon-studio.core/1","event":"ready","url":"http://127.0.0.1:1/api","version":"x","pid":1}"#,
            "[studio] GET / 200",
        ] {
            assert!(parse_handshake(bad).is_err(), "{bad}");
        }
    }

    #[test]
    fn frozen_core_beside_the_shell_wins() {
        let dir = std::env::temp_dir().join(format!("hs-core-{}", std::process::id()));
        std::fs::create_dir_all(dir.join("core")).unwrap();
        std::fs::write(dir.join("core").join(CORE_NAME), b"").unwrap();
        assert_eq!(locate(std::slice::from_ref(&dir)).unwrap(), Launch::Frozen(dir.join("core").join(CORE_NAME)));
        std::fs::remove_dir_all(dir).unwrap();
    }
}
