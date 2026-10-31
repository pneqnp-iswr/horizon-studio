//! Saving files the editor exports (projects, .hmod packages, source ZIPs).
//!
//! `write_atomically` never leaves a half-written target: the bytes go to a uniquely named
//! temporary file in the same folder, are flushed to disk (`sync_all`), then replace the
//! target in one rename; on Windows the rename is `MoveFileExW` with `MOVEFILE_WRITE_THROUGH`,
//! on Unix the folder is synced afterwards. Any failure removes the temporary file and leaves
//! the previous target untouched. This is crash- and interruption-safe for the target's
//! contents; it cannot promise more than the file system and disk do on power loss.

use std::fs::{self, File, OpenOptions};
use std::io::{self, Write};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

pub const MAX_SAVE_BYTES: usize = 256 * 1024 * 1024;
static COUNTER: AtomicU64 = AtomicU64::new(0);

/// A file name the page suggests for a native "Save as" dialog: a bare name, no paths.
pub fn suggested_name(raw: Option<&str>) -> Result<String, String> {
    let name = percent_encoding::percent_decode_str(raw.unwrap_or("export")).decode_utf8_lossy().trim().to_string();
    let valid = !name.is_empty()
        && name.chars().count() <= 160
        && !name.starts_with('.')
        && !name.ends_with('.')
        && !name.chars().any(|c| c.is_control() || matches!(c, '/' | '\\' | ':' | '*' | '?' | '"' | '<' | '>' | '|'));
    if valid {
        Ok(name)
    } else {
        Err(format!("Refusing unsafe file name {name:?}"))
    }
}

pub fn filter_for(name: &str) -> Option<(&'static str, &'static str)> {
    if name.ends_with(".hmod") {
        Some(("Horizon content mod", "hmod"))
    } else if name.ends_with(".hstudio.json") {
        Some(("Horizon Studio project", "json"))
    } else if name.ends_with(".zip") {
        Some(("ZIP archive", "zip"))
    } else {
        None
    }
}

pub fn check_size(len: usize) -> Result<(), String> {
    if len == 0 || len > MAX_SAVE_BYTES {
        Err(format!("Refusing to save {len} bytes (1 byte to {MAX_SAVE_BYTES} bytes)"))
    } else {
        Ok(())
    }
}

fn temporary_for(path: &Path) -> io::Result<PathBuf> {
    let name = path.file_name().ok_or_else(|| io::Error::new(io::ErrorKind::InvalidInput, "no file name"))?;
    let nanos = SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.subsec_nanos()).unwrap_or(0);
    let unique = format!(".{}.{}-{}-{nanos}.hs-tmp", std::process::id(), COUNTER.fetch_add(1, Ordering::Relaxed), name.len());
    // Short temporary names keep long target names under the platform's path limits.
    Ok(path.with_file_name(unique))
}

#[cfg(windows)]
fn replace(from: &Path, to: &Path) -> io::Result<()> {
    use std::os::windows::ffi::OsStrExt;
    use windows_sys::Win32::Storage::FileSystem::{MoveFileExW, MOVEFILE_REPLACE_EXISTING, MOVEFILE_WRITE_THROUGH};
    let wide = |p: &Path| p.as_os_str().encode_wide().chain(Some(0)).collect::<Vec<u16>>();
    let (from, to) = (wide(from), wide(to));
    // SAFETY: both buffers are NUL-terminated UTF-16 strings that outlive the call.
    let ok = unsafe { MoveFileExW(from.as_ptr(), to.as_ptr(), MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH) };
    if ok == 0 {
        Err(io::Error::last_os_error())
    } else {
        Ok(())
    }
}

#[cfg(not(windows))]
fn replace(from: &Path, to: &Path) -> io::Result<()> {
    fs::rename(from, to)?;
    if let Some(dir) = to.parent() {
        // Persist the directory entry too; ignore file systems that cannot sync a directory.
        if let Ok(handle) = File::open(if dir.as_os_str().is_empty() { Path::new(".") } else { dir }) {
            let _ = handle.sync_all();
        }
    }
    Ok(())
}

/// Writes `bytes` to `path` atomically; see the module documentation.
pub fn write_atomically(path: &Path, bytes: &[u8]) -> io::Result<()> {
    write_atomically_with(path, bytes, |_| Ok(()))
}

/// `before_replace` runs after the temporary file is complete and synced; tests use it to
/// simulate an interruption at the last moment.
pub fn write_atomically_with(path: &Path, bytes: &[u8], before_replace: impl FnOnce(&Path) -> io::Result<()>) -> io::Result<()> {
    let temporary = temporary_for(path)?;
    let result = (|| {
        let mut file = OpenOptions::new().write(true).create_new(true).open(&temporary)?;
        file.write_all(bytes)?;
        file.sync_all()?;
        drop(file);
        before_replace(&temporary)?;
        replace(&temporary, path)
    })();
    if result.is_err() {
        let _ = fs::remove_file(&temporary);
    }
    result
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Arc;
    use std::thread;

    fn scratch(name: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!("hs-files-{name}-{}-{}", std::process::id(), COUNTER.fetch_add(1, Ordering::Relaxed)));
        fs::create_dir_all(&dir).unwrap();
        dir
    }

    fn leftovers(dir: &Path) -> Vec<String> {
        fs::read_dir(dir).unwrap().map(|e| e.unwrap().file_name().to_string_lossy().into_owned())
            .filter(|n| n.ends_with(".hs-tmp")).collect()
    }

    #[test]
    fn save_names_are_bare_file_names() {
        assert_eq!(suggested_name(Some("ruby_demo.hmod")).unwrap(), "ruby_demo.hmod");
        assert_eq!(suggested_name(Some("my%20mod-source.zip")).unwrap(), "my mod-source.zip");
        assert_eq!(suggested_name(Some("%D0%BC%D0%BE%D0%B4.hmod")).unwrap(), "мод.hmod");
        for bad in ["../evil.hmod", "a%2Fb.hmod", "C:%5Cx.hmod", ".hidden", "", "a\u{7}b", "trailing.", "con<1>.zip"] {
            assert!(suggested_name(Some(bad)).is_err(), "{bad}");
        }
        assert!(suggested_name(Some(&"x".repeat(161))).is_err());
        assert_eq!(filter_for("x.hstudio.json"), Some(("Horizon Studio project", "json")));
        assert_eq!(filter_for("x.txt"), None);
    }

    #[test]
    fn size_limits() {
        assert!(check_size(0).is_err());
        assert!(check_size(1).is_ok());
        assert!(check_size(MAX_SAVE_BYTES).is_ok());
        assert!(check_size(MAX_SAVE_BYTES + 1).is_err());
    }

    #[test]
    fn replaces_an_existing_file_and_leaves_no_temporary() {
        let dir = scratch("replace");
        let target = dir.join("out.hmod");
        fs::write(&target, b"old").unwrap();
        write_atomically(&target, b"new").unwrap();
        assert_eq!(fs::read(&target).unwrap(), b"new");
        write_atomically(&target, b"newer").unwrap();
        assert_eq!(fs::read(&target).unwrap(), b"newer");
        assert!(leftovers(&dir).is_empty());
        fs::remove_dir_all(dir).unwrap();
    }

    #[test]
    fn unicode_and_long_names() {
        let dir = scratch("names");
        for name in ["модель ✓ 鉱石.hmod".to_string(), format!("{}.hstudio.json", "a".repeat(150))] {
            let target = dir.join(&name);
            write_atomically(&target, name.as_bytes()).unwrap();
            assert_eq!(fs::read(&target).unwrap(), name.as_bytes(), "{name}");
        }
        assert!(leftovers(&dir).is_empty());
        fs::remove_dir_all(dir).unwrap();
    }

    #[test]
    fn an_interruption_before_the_replace_keeps_the_old_file() {
        let dir = scratch("interrupt");
        let target = dir.join("project.hstudio.json");
        fs::write(&target, b"previous good copy").unwrap();
        let error = write_atomically_with(&target, b"half finished", |temporary| {
            assert!(temporary.is_file(), "the complete temporary exists until the replace");
            Err(io::Error::other("power cut"))
        });
        assert!(error.is_err());
        assert_eq!(fs::read(&target).unwrap(), b"previous good copy");
        assert!(leftovers(&dir).is_empty(), "the temporary file is removed");
        fs::remove_dir_all(dir).unwrap();
    }

    #[test]
    fn a_missing_folder_fails_cleanly() {
        let dir = scratch("missing");
        let target = dir.join("no-such-folder").join("x.hmod");
        assert!(write_atomically(&target, b"x").is_err());
        assert!(!target.exists());
        fs::remove_dir_all(dir).unwrap();
    }

    #[test]
    fn concurrent_saves_never_mix_contents() {
        let dir = scratch("concurrent");
        let target = Arc::new(dir.join("shared.hmod"));
        let payloads: Vec<Vec<u8>> = (0..8u8).map(|i| vec![i; 64 * 1024]).collect();
        let handles: Vec<_> = payloads.iter().cloned().map(|payload| {
            let target = Arc::clone(&target);
            thread::spawn(move || {
                for _ in 0..10 {
                    // On Windows a concurrent replace can be refused while another holds the target; the
                    // writer then reports an error and the target keeps one complete payload.
                    let _ = write_atomically(&target, &payload);
                }
            })
        }).collect();
        for handle in handles {
            handle.join().unwrap();
        }
        let content = fs::read(&*target).unwrap();
        assert!(payloads.contains(&content), "the file holds exactly one complete payload");
        assert!(leftovers(&dir).is_empty());
        fs::remove_dir_all(dir).unwrap();
    }
}
