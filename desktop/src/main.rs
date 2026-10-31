#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
//! Horizon Studio desktop shell: one native window hosting the editor, which the bundled
//! Python core serves on a private loopback port. No external browser and no launcher
//! window are involved. Architecture and trade-offs: docs/adr/0002-desktop-shell.md.

mod core;
mod files;
mod options;

use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};

use serde_json::{json, Value};
use tauri::ipc::{CapabilityBuilder, InvokeBody, Request};
use tauri::webview::{NewWindowResponse, PageLoadEvent};
use tauri::{AppHandle, Manager, RunEvent, Url, WebviewUrl, WebviewWindowBuilder};
use tauri_plugin_dialog::DialogExt;
use tauri_plugin_opener::OpenerExt;

use crate::core::Core;
use crate::files::{check_size, filter_for, suggested_name, write_atomically};
use crate::options::Options;

const MAIN: &str = "main";
const CORE_START_TIMEOUT: Duration = Duration::from_secs(60);
const CORE_STOP_TIMEOUT: Duration = Duration::from_secs(10);

#[derive(Default)]
struct Timeline {
    core_ready_ms: Option<u128>,
    page_loaded_ms: Option<u128>,
    editor_ready_ms: Option<u128>,
    core: Option<Value>,
    page: Option<Value>,
    failure: Option<String>,
}

struct Shell {
    started: Instant,
    options: Options,
    /// The only non-shell origin the window may show, known once the core is ready.
    origin: Arc<Mutex<Option<Url>>>,
    core: Mutex<Option<Core>>,
    timeline: Mutex<Timeline>,
    log: Option<PathBuf>,
    finished: AtomicBool,
}

impl Shell {
    fn elapsed(&self) -> u128 {
        self.started.elapsed().as_millis()
    }
}

/// Pages bundled into the shell (the splash): `tauri://localhost` or, on Windows,
/// `http(s)://tauri.localhost`.
fn is_shell_page(url: &Url) -> bool {
    match url.scheme() {
        "tauri" => url.host_str() == Some("localhost"),
        "http" | "https" => url.host_str() == Some("tauri.localhost"),
        _ => false,
    }
}

fn is_core_page(url: &Url, origin: &Option<Url>) -> bool {
    origin.as_ref().is_some_and(|core| {
        url.scheme() == "http" && url.host_str() == Some("127.0.0.1") && url.port() == core.port()
    })
}

fn navigation_allowed(url: &Url, origin: &Mutex<Option<Url>>) -> bool {
    is_shell_page(url) || is_core_page(url, &origin.lock().unwrap())
}

/// Editor -> shell: native "Save as" for exports and project files. The bytes arrive as
/// the raw request body; the suggested file name in the `x-file-name` header.
#[tauri::command]
async fn save_file(app: AppHandle, request: Request<'_>) -> Result<Value, String> {
    let InvokeBody::Raw(bytes) = request.body() else {
        return Err("Expected the file bytes as the request body".into());
    };
    check_size(bytes.len())?;
    let name = suggested_name(request.headers().get("x-file-name").and_then(|v| v.to_str().ok()))?;
    // Test builds only (cargo feature `e2e`, never shipped): the native dialog cannot be driven by
    // WebDriver, so desktop E2E answers it from the environment instead.
    #[cfg(feature = "e2e")]
    if let Some(answer) = e2e_dialog_answer(&name) {
        return finish_save(answer, bytes);
    }
    let mut dialog = app.dialog().file().set_file_name(&name);
    if let Some(window) = app.get_webview_window(MAIN) {
        dialog = dialog.set_parent(&window);
    }
    if let Some((label, extension)) = filter_for(&name) {
        dialog = dialog.add_filter(label, &[extension]);
    }
    let chosen = match dialog.blocking_save_file() {
        Some(target) => Some(target.into_path().map_err(|e| e.to_string())?),
        None => None,
    };
    finish_save(chosen, bytes)
}

/// The dialog's answer: `None` is a cancelled dialog and writes nothing.
fn finish_save(chosen: Option<PathBuf>, bytes: &[u8]) -> Result<Value, String> {
    let Some(path) = chosen else {
        return Ok(json!({ "saved": false }));
    };
    write_atomically(&path, bytes).map_err(|e| format!("Could not save {}: {e}", path.display()))?;
    let saved = path.file_name().map(|n| n.to_string_lossy().into_owned());
    Ok(json!({ "saved": true, "name": saved, "bytes": bytes.len() }))
}

#[cfg(feature = "e2e")]
fn e2e_dialog_answer(name: &str) -> Option<Option<PathBuf>> {
    if std::env::var_os("HORIZON_STUDIO_E2E_CANCEL_SAVE").is_some() {
        return Some(None);
    }
    std::env::var_os("HORIZON_STUDIO_E2E_SAVE_DIR").map(|dir| Some(PathBuf::from(dir).join(name)))
}

/// Editor -> shell: the editor finished booting. Returns what the status bar shows.
#[tauri::command]
fn desktop_ready(app: AppHandle, info: Value) -> Value {
    let shell = app.state::<Shell>();
    let mut timeline = shell.timeline.lock().unwrap();
    if timeline.editor_ready_ms.is_none() {
        timeline.editor_ready_ms = Some(shell.elapsed());
        timeline.page = Some(info);
        if let Some(report) = &shell.options.smoke_report {
            // `<report>.ready` tells an external probe the window is ready for a screenshot.
            let mut ready = report.clone().into_os_string();
            ready.push(".ready");
            let _ = std::fs::write(ready, format!("{{\"editor_ready_ms\": {}}}\n", shell.elapsed()));
            let hold = shell.options.smoke_hold;
            let handle = app.clone();
            thread::spawn(move || {
                thread::sleep(hold);
                finish(&handle, None);
            });
        }
    }
    json!({
        "shell": env!("CARGO_PKG_VERSION"),
        "core": timeline.core.as_ref().and_then(|c| c.get("version").cloned()),
        "platform": std::env::consts::OS,
        "startup_ms": timeline.editor_ready_ms,
    })
}

fn show_failure(app: &AppHandle, message: &str) {
    let shell = app.state::<Shell>();
    shell.timeline.lock().unwrap().failure = Some(message.to_string());
    let detail = json!({ "message": message, "log": shell.log.as_ref().map(|p| p.display().to_string()) });
    if let Some(window) = app.get_webview_window(MAIN) {
        let _ = window.eval(format!("window.horizonSplash && window.horizonSplash.fail({detail})"));
    }
    if shell.options.smoke() {
        finish(app, Some(message.to_string()));
    }
}

/// Starts the core off the UI thread, then points the window at the editor.
fn boot(app: AppHandle) {
    let shell = app.state::<Shell>();
    let mut dirs = Vec::new();
    if let Ok(dir) = app.path().resource_dir() {
        dirs.push(dir);
    }
    if let Some(dir) = std::env::current_exe().ok().and_then(|exe| exe.parent().map(Path::to_path_buf)) {
        dirs.push(dir);
    }
    let started = core::locate(&dirs).and_then(|launch| Core::start(launch, shell.log.as_deref(), CORE_START_TIMEOUT));
    let core = match started {
        Ok(core) => core,
        Err(error) => return show_failure(&app, &error),
    };
    let url = core.url.clone();
    // Editor commands are granted to this exact origin and window only.
    let capability = CapabilityBuilder::new("editor")
        .remote(format!("{}*", url.as_str()))
        .local(false)
        .window(MAIN)
        .permission("allow-desktop-ready")
        .permission("allow-save-file");
    if let Err(error) = app.add_capability(capability) {
        return show_failure(&app, &format!("Could not grant the editor its commands: {error}"));
    }
    {
        let mut timeline = shell.timeline.lock().unwrap();
        timeline.core_ready_ms = Some(shell.elapsed());
        timeline.core = Some(json!({
            "launch": core.launch.kind(), "pid": core.pid, "version": core.version, "protocol": core::PROTOCOL,
        }));
    }
    *shell.origin.lock().unwrap() = Some(url.clone());
    *shell.core.lock().unwrap() = Some(core);
    match app.get_webview_window(MAIN) {
        Some(window) => {
            if let Err(error) = window.navigate(url) {
                show_failure(&app, &format!("Could not open the editor: {error}"));
            }
        }
        None => show_failure(&app, "The main window is gone"),
    }
}

/// Stops the core and, in smoke mode, writes the report and exits.
fn finish(app: &AppHandle, error: Option<String>) {
    let shell = app.state::<Shell>();
    if shell.finished.swap(true, Ordering::SeqCst) {
        return;
    }
    let stopped = shell.core.lock().unwrap().take().map(|core| core.stop(CORE_STOP_TIMEOUT));
    if let Some(path) = &shell.options.smoke_report {
        let timeline = shell.timeline.lock().unwrap();
        let clean = stopped.is_none_or(|(code, killed, _)| code == Some(0) && !killed);
        let error = error.or_else(|| (!clean).then(|| "The core did not shut down cleanly".to_string()));
        let report = json!({
            "schema": "horizon-studio.desktop-smoke/1",
            "ok": error.is_none(),
            "error": error,
            "shell": {
                "version": env!("CARGO_PKG_VERSION"),
                "os": std::env::consts::OS,
                "arch": std::env::consts::ARCH,
                // A packaged build must never be a test build; scripts/desktop_probe.py checks this.
                "test_build": cfg!(feature = "e2e"),
            },
            "core": timeline.core,
            "page": timeline.page,
            "window": { "width": shell.options.window_size.0, "height": shell.options.window_size.1 },
            "timings_ms": {
                "core_ready": timeline.core_ready_ms,
                "page_loaded": timeline.page_loaded_ms,
                "editor_ready": timeline.editor_ready_ms,
                "core_stop": stopped.map(|(_, _, took)| took.as_millis()),
            },
            "shutdown": stopped.map(|(code, killed, _)| json!({ "core_exit_code": code, "killed": killed })),
        });
        let text = serde_json::to_string_pretty(&report).unwrap_or_default() + "\n";
        if let Err(write_error) = std::fs::write(path, text) {
            eprintln!("Could not write the smoke report {}: {write_error}", path.display());
        }
        app.exit(if report["ok"] == json!(true) { 0 } else { 1 });
    }
}

fn main() {
    let options = match Options::parse(std::env::args().skip(1)) {
        Ok(options) => options,
        Err(error) => {
            eprintln!("Horizon Studio: {error}");
            std::process::exit(2);
        }
    };
    let origin = Arc::new(Mutex::new(None));
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![desktop_ready, save_file])
        .setup({
            let origin = origin.clone();
            move |app| {
                let log = app.path().app_log_dir().ok().and_then(|dir| {
                    std::fs::create_dir_all(&dir).ok()?;
                    Some(dir.join("core.log"))
                });
                app.manage(Shell {
                    started: Instant::now(),
                    options: options.clone(),
                    origin: origin.clone(),
                    core: Mutex::new(None),
                    timeline: Mutex::new(Timeline::default()),
                    log,
                    finished: AtomicBool::new(false),
                });
                let (width, height) = options.window_size;
                let guard = origin.clone();
                let opener = app.handle().clone();
                WebviewWindowBuilder::new(app, MAIN, WebviewUrl::App("index.html".into()))
                    .title("Horizon Studio")
                    .inner_size(width, height)
                    .min_inner_size(960.0, 600.0)
                    .center()
                    .on_navigation(move |url| navigation_allowed(url, &guard))
                    .on_new_window(move |url, _features| {
                        // Links that open a new window (documentation, the native mod
                        // template) go to the system browser; the shell never hosts them.
                        if url.scheme() == "https" {
                            let _ = opener.opener().open_url(url.as_str(), None::<&str>);
                        }
                        NewWindowResponse::Deny
                    })
                    .on_page_load(|window, payload| {
                        if payload.event() == PageLoadEvent::Finished {
                            let shell = window.state::<Shell>();
                            if is_core_page(payload.url(), &shell.origin.lock().unwrap()) {
                                let mut timeline = shell.timeline.lock().unwrap();
                                timeline.page_loaded_ms.get_or_insert(shell.elapsed());
                            } else if let Some(message) = shell.timeline.lock().unwrap().failure.clone() {
                                let detail = json!({ "message": message, "log": shell.log.as_ref().map(|p| p.display().to_string()) });
                                let _ = window.eval(format!("window.horizonSplash && window.horizonSplash.fail({detail})"));
                            }
                        }
                    })
                    .build()?;
                let handle = app.handle().clone();
                thread::spawn(move || boot(handle));
                if options.smoke() {
                    let handle = app.handle().clone();
                    let timeout = options.smoke_timeout;
                    thread::spawn(move || {
                        thread::sleep(timeout);
                        finish(&handle, Some(format!("The editor did not report ready within {} s", timeout.as_secs())));
                    });
                }
                Ok(())
            }
        })
        .build(tauri::generate_context!())
        .expect("failed to build the Horizon Studio shell");
    app.run(|app, event| {
        if let RunEvent::Exit = event {
            if let Some(shell) = app.try_state::<Shell>() {
                if let Some(core) = shell.core.lock().unwrap().take() {
                    core.stop(CORE_STOP_TIMEOUT);
                }
            }
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn navigation_is_limited_to_the_splash_and_the_core() {
        let origin = Mutex::new(None);
        let url = |s: &str| Url::parse(s).unwrap();
        assert!(navigation_allowed(&url("tauri://localhost/index.html"), &origin));
        assert!(navigation_allowed(&url("http://tauri.localhost/index.html"), &origin));
        assert!(!navigation_allowed(&url("http://127.0.0.1:40123/"), &origin), "unknown before the handshake");
        *origin.lock().unwrap() = Some(url("http://127.0.0.1:40123/"));
        assert!(navigation_allowed(&url("http://127.0.0.1:40123/"), &origin));
        for denied in [
            "http://127.0.0.1:8787/",
            "http://localhost:40123/",
            "https://127.0.0.1:40123/",
            "https://github.com/",
            "file:///etc/passwd",
            "http://tauri.localhost.example.com/",
        ] {
            assert!(!navigation_allowed(&url(denied), &origin), "{denied}");
        }
    }

    #[test]
    fn a_cancelled_dialog_writes_nothing() {
        assert_eq!(finish_save(None, b"bytes").unwrap(), json!({ "saved": false }));
    }
}
