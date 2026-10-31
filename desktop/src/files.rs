//! Saving files the editor exports (projects, .hmod packages, source ZIPs).
//!
//! `write_atomically` never leaves a half-written target: the bytes go to a uniquely named
//! temporary file in the same folder, are flushed to disk (`sync_all`), then replace the
//! target in one rename; on Windows the rename is `MoveFileExW` with `MOVEFILE_WRITE_THROUGH`,
//! on Unix the folder is synced afterwards. Any failure removes the temporary file and leaves
//! the previous target untouched. This is crash- and interruption-safe for the target's
//! contents; it cannot promise more than the file system and disk do on power loss.

use std::fs::{self, OpenOptions};
use std::io::{self, Write};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

pub const MAX_SAVE_BYTES: usize = 256 * 1024 * 1024;
static COUNTER: AtomicU64 = AtomicU64::new(0);

/// What the editor saves; nothing else is offered in a Save dialog (no executables or scripts).
const SAVE_TYPES: [&str; 3] = [".hmod", ".hstudio.json", ".zip"];

/// Invisible format characters (bidirectional overrides, zero-width marks) that can disguise a name.
fn is_format_char(c: char) -> bool {
    matches!(c, '\u{00AD}' | '\u{061C}' | '\u{180E}' | '\u{200B}'..='\u{200F}' | '\u{202A}'..='\u{202E}'
        | '\u{2060}'..='\u{2064}' | '\u{2066}'..='\u{206F}' | '\u{FEFF}' | '\u{FFF9}'..='\u{FFFB}')
}

/// Names Windows reserves for devices, with or without an extension (`NUL.zip`).
fn is_reserved_on_windows(name: &str) -> bool {
    let stem = name.split('.').next().unwrap_or("").trim_end().to_ascii_uppercase();
    matches!(stem.as_str(), "CON" | "PRN" | "AUX" | "NUL" | "CONIN$" | "CONOUT$")
        || (stem.len() == 4
            && (stem.starts_with("COM") || stem.starts_with("LPT"))
            && stem[3..].chars().all(|c| c.is_ascii_digit() || matches!(c, '¹' | '²' | '³')))
}

/// A file name the page suggests for a native "Save as" dialog: a bare name, no paths, and
/// one of the types the editor saves.
pub fn suggested_name(raw: Option<&str>) -> Result<String, String> {
    let name = percent_encoding::percent_decode_str(raw.unwrap_or("export")).decode_utf8_lossy().trim().to_string();
    let valid = !name.is_empty()
        && name.chars().count() <= 160
        && !name.starts_with('.')
        && !name.ends_with('.')
        && SAVE_TYPES.iter().any(|ext| name.len() > ext.len() && name.to_ascii_lowercase().ends_with(ext))
        && !is_reserved_on_windows(&name)
        && !name.chars().any(|c| c.is_control() || is_format_char(c) || matches!(c, '/' | '\\' | ':' | '*' | '?' | '"' | '<' | '>' | '|'));
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

/// `\\?\` form of an absolute Windows path, so paths longer than MAX_PATH (260) work without the
/// process manifest opting in. Relative and already verbatim paths are returned unchanged.
#[cfg_attr(not(windows), allow(dead_code))]
fn verbatim(path: &Path) -> std::ffi::OsString {
    let unchanged = path.as_os_str().to_os_string();
    // A verbatim path is taken literally: only rewrite plain, normalized Unicode paths.
    let Some(text) = path.to_str() else { return unchanged };
    let bytes = text.as_bytes();
    if text.starts_with("\\\\?\\")
        || text.contains('/')
        || text.split('\\').any(|part| part == "." || part == "..")
    {
        unchanged
    } else if bytes.len() >= 3 && bytes[0].is_ascii_alphabetic() && bytes[1] == b':' && bytes[2] == b'\\' {
        format!("\\\\?\\{text}").into()
    } else if let Some(unc) = text.strip_prefix("\\\\") {
        format!("\\\\?\\UNC\\{unc}").into()
    } else {
        unchanged
    }
}

#[cfg(windows)]
fn replace(from: &Path, to: &Path) -> io::Result<()> {
    use std::os::windows::ffi::OsStrExt;
    use windows_sys::Win32::Storage::FileSystem::{MoveFileExW, MOVEFILE_REPLACE_EXISTING, MOVEFILE_WRITE_THROUGH};
    let wide = |p: &Path| verbatim(p).encode_wide().chain(Some(0)).collect::<Vec<u16>>();
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
        if let Ok(handle) = fs::File::open(if dir.as_os_str().is_empty() { Path::new(".") } else { dir }) {
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
        // Replacing a file keeps its permissions (a private 0600 project stays private). Not on
        // Windows, where the only bit is read-only and a read-only target cannot be replaced anyway.
        #[cfg(unix)]
        if let Ok(previous) = fs::metadata(path) {
            file.set_permissions(previous.permissions())?;
        }
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
        assert_eq!(suggested_name(Some("Ruby.HMOD")).unwrap(), "Ruby.HMOD");
        for bad in ["../evil.hmod", "a%2Fb.hmod", "C:%5Cx.hmod", ".hidden", "", "a\u{7}b.zip", "trailing.", "con<1>.zip"] {
            assert!(suggested_name(Some(bad)).is_err(), "{bad}");
        }
        // Only what the editor saves: no executables or scripts, however they are disguised.
        for bad in ["Update.exe", "run.bat", "start.desktop", "notes.txt", ".hmod", "ruby.hmod.exe",
            "invoice\u{202E}domh.exe", "a\u{200B}b.hmod", "x\u{FEFF}.zip", "NUL.zip", "com1.hmod", "Lpt9.hstudio.json", "CON"] {
            assert!(suggested_name(Some(bad)).is_err(), "{bad:?}");
        }
        assert!(suggested_name(Some("console.hmod")).is_ok(), "only exact device names are reserved");
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
    fn verbatim_paths_for_long_windows_paths() {
        let v = |s: &str| verbatim(Path::new(s)).to_string_lossy().into_owned();
        assert_eq!(v(r"C:\Users\a\x.hmod"), r"\\?\C:\Users\a\x.hmod");
        assert_eq!(v(r"\\server\share\x.hmod"), r"\\?\UNC\server\share\x.hmod");
        for same in [r"\\?\C:\x.hmod", "relative.hmod", "C:/mixed/x.hmod", r"C:\a\..\x.hmod"] {
            assert_eq!(v(same), same);
        }
    }

    #[test]
    fn saves_beyond_the_old_260_character_limit() {
        let dir = scratch("long");
        let mut folder = dir.clone();
        while folder.as_os_str().len() < 300 {
            folder = folder.join("a_rather_long_folder_name_for_paths");
        }
        fs::create_dir_all(&folder).unwrap();
        let target = folder.join("project.hstudio.json");
        assert!(target.as_os_str().len() > 300);
        write_atomically(&target, b"first").unwrap();
        write_atomically(&target, b"second").unwrap();
        assert_eq!(fs::read(&target).unwrap(), b"second");
        assert!(leftovers(&folder).is_empty());
        fs::remove_dir_all(dir).unwrap();
    }

    #[cfg(unix)]
    #[test]
    fn replacing_keeps_the_target_permissions() {
        use std::os::unix::fs::PermissionsExt;
        let dir = scratch("mode");
        let target = dir.join("private.hstudio.json");
        fs::write(&target, b"secret").unwrap();
        fs::set_permissions(&target, fs::Permissions::from_mode(0o600)).unwrap();
        write_atomically(&target, b"still secret").unwrap();
        assert_eq!(fs::metadata(&target).unwrap().permissions().mode() & 0o777, 0o600);
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
