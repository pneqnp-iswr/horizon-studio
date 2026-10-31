# Desktop shell security and lifecycle review (engineering cycle 2)

Scope: `desktop/src/main.rs`, `desktop/src/core.rs`, `desktop/src/files.rs`, the Tauri capabilities and CSP,
`desktop_bridge.js`, `editor_api.js`, `launcher.py` (`--serve`) and `security/request_policy.py` as used by `studio.py`.

Method: an independent read of the code (a separate reviewer given the files, not our conclusions), then every finding
re-checked against the source before it was accepted, fixed with a regression test, and the fixes exercised on the real
desktop window (`tests/desktop/desktop.e2e.cjs`). Threat model: a malicious web page, another local user or process on
the same machine, and a crashing or hung core. Not in scope: a compromised operating system account, physical access.

## Findings and fixes

| ID | Severity | Finding (verified) | Fix | Test |
|---|---|---|---|---|
| V1 | Medium | Any local process could `GET /api/session` (no Origin header passes the browser checks), then use the API, e.g. overwrite autosaved workspaces | The core sends its token to the shell in the handshake over the private stdout pipe; the editor gets it through the `core_session` command, granted only to the core's origin; in desktop mode the core answers `/api/session` with 403. Browser mode (0.7 EXE, `python studio.py`) is unchanged: its threat model is cross-site pages, which the Host/Origin/Fetch-Metadata checks cover | `tests/test_launcher.py` (403 without the token, authorized with it), `core.rs` handshake tests (missing or malformed tokens refused, never echoed), desktop E2E scenario 1 |
| V2 | Low–Medium | The shell did not notice the core dying; its origin stayed trusted, so a process later bound to that port would be shown with the editor's grants | The stdout reader reports the exit; the shell clears the origin and token and navigates to the failure screen (deliberate stops are told apart) | `core.rs` `an_unexpected_exit_after_the_handshake_is_reported`; desktop E2E "a core that dies under the editor" |
| V3 | Low | A core that closed stdout but kept running made startup wait forever | Kill before wait | `a_core_that_closes_stdout_but_keeps_running_does_not_hang_startup` |
| V4 | Low | A Save dialog could be offered for any type (`Update.exe`), with bidirectional-override or zero-width characters, or a Windows device name | Only `.hmod`, `.hstudio.json`, `.zip`; format characters and device names refused | `files.rs` `save_names_are_bare_file_names` |
| V5 | Low | Replacing a file on Unix reset its permissions (0600 became 0644) | The temporary file takes the target's permissions before the rename | `replacing_keeps_the_target_permissions` |
| V6 | Low | Targets over 260 characters failed on Windows (`MoveFileExW` without `\\?\`) | Normalized absolute paths are passed in `\\?\` form | `verbatim_paths_for_long_windows_paths`, `saves_beyond_the_old_260_character_limit` (runs on Windows CI) |
| V7 | Low | Repeated `save_file` calls could open many dialogs, each blocking a runtime worker | One dialog at a time | not automated: it needs two native dialogs; reviewed in `main.rs` (`saving` flag) |
| V8 | Low | The shell-page check accepted `http(s)://tauri.localhost` on any port and platform | Exactly this platform's origin with no port | `navigation_is_limited_to_the_splash_and_the_core` |
| S1 | Medium on Windows (confirmed in CPython's source, exploit not attempted) | `HTTPServer` sets `SO_REUSEADDR`; on Windows another process could bind the same port | The desktop core uses an exclusive socket: no `SO_REUSEADDR`, `SO_EXCLUSIVEADDRUSE` on Windows. The browser mode keeps its fixed port 8787 and its old behaviour so a restart can rebind it | `test_the_desktop_core_port_cannot_be_shared` |

## Accepted or open

- **Links:** `https` links open in the system browser without a host allowlist. Reaching that requires script in the
  editor page first (CSP `default-src 'self'`); an allowlist would break documentation links. Revisit with S3.
- **CSP `'unsafe-inline'`** for scripts and styles remains because `index.html` has an inline script; moving it to a
  file would allow a strict CSP. Open.
- **S2:** a window closed while the core is still starting relies on stdin EOF; a core that hangs before reading stdin
  would be orphaned. A Windows Job Object with kill-on-close would cover it. Open, not observed.
- **S3:** the editor's `innerHTML` uses were not audited in this review. Open.
- The exit handler may block the main thread up to 10 s while the core stops; `core.log` is created with default
  permissions and truncated by a second instance; a failed save reports the full path to the page. Accepted for the
  preview.

## Checked and sound

Navigation guard (exact `http://127.0.0.1:<port>` of this core), runtime capability scoped to that origin and the main
window, ACL on every command, empty splash capability, IPC only in the main frame, `X-Frame-Options: DENY`, literal
Host allowlist against DNS rebinding, `Origin` must match, `Sec-Fetch-Site` same-origin or none, 256-bit token compared
in constant time, strict content types forcing CORS preflight, no CORS headers, no token in URLs, logs or the window
title, handshake URL strictly validated, the reported PID never used to kill anything, stdout drained, child processes
reaped, test-only hooks compiled out of release builds, the single `unsafe` block (`MoveFileExW`) matching its
signature.
