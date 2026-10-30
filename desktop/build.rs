fn main() {
    // The editor page reaches the shell only through these commands. Declaring them in an
    // app manifest makes every command subject to the ACL (see capabilities/ and the
    // runtime "editor" capability in main.rs, limited to the core's loopback origin).
    tauri_build::try_build(
        tauri_build::Attributes::new()
            .app_manifest(tauri_build::AppManifest::new().commands(&["desktop_ready", "save_file"])),
    )
    .expect("failed to run tauri-build");
}
