# Desktop shell security and lifecycle review (engineering cycles 2 and 3)

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
| V7 | Low | Repeated `save_file` calls could open many dialogs, each blocking a runtime worker | One dialog at a time | `only_one_dialog_opens_even_when_requests_race` (cycle 3) |
| V8 | Low | The shell-page check accepted `http(s)://tauri.localhost` on any port and platform | Exactly this platform's origin with no port | `navigation_is_limited_to_the_splash_and_the_core` |
| S1 | Medium on Windows (confirmed in CPython's source, exploit not attempted) | `HTTPServer` sets `SO_REUSEADDR`; on Windows another process could bind the same port | The desktop core uses an exclusive socket: no `SO_REUSEADDR`, `SO_EXCLUSIVEADDRUSE` on Windows. The browser mode keeps its fixed port 8787 and its old behaviour so a restart can rebind it | `test_the_desktop_core_port_cannot_be_shared` |

## Accepted or open

Updated after the second review below.

- **Links:** fixed in V9.
- **CSP `'unsafe-inline'` for scripts:** fixed in C1.
- **S2:** fixed for Windows in S2.
- **S3:** fixed with the audit below.
- **Exit wait and log permissions:** fixed in V10 and V11.
- **Failed saves:** a failed save reports the full path to the page. Accepted (the page is the person's own editor).

## Second review (engineering cycle 3)

Scope: what the first review left open, plus the editor's DOM sinks (`*.js`), the core's CSP (`studio.py`), and the
Preview Bridge's process handling (`studio_core/preview_bridge.py`).

| ID | Severity | Finding (verified) | Fix | Test |
|---|---|---|---|---|
| S2 | Medium | If the shell crashed or was killed, its `Drop` never ran. A core that was hung (not reading stdin) was then orphaned, and so was anything the core had started (a Preview Bridge game). EOF handling only covers a core that is still responsive | Windows: the core runs in a Job Object with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, and Windows closes the handle when the shell exits for any reason. Linux/macOS: the core leads a process group, and every stop kills the group. Limit, stated in `tree.rs`: if the shell is SIGKILLed on Linux/macOS, a *hung* core is not stopped (no kill-on-close; `PR_SET_PDEATHSIG` follows the spawning thread, a short-lived boot thread here). The smoke report records `process_tree` | `tree.rs` `killing_the_tree_stops_the_core_and_what_it_started`, `dropping_the_owner_stops_the_tree_like_a_crashed_shell_would` (both on Linux and Windows CI), `core.rs` `stopping_the_core_also_stops_what_it_started` |
| S3-1 | Medium | A structure's `size` and `rotation` from an opened project file reached `innerHTML` unescaped: a hostile `.hstudio.json` injected elements. Their inline handlers did not run, because the CSP blocked them | Escaped | `tests/e2e/editor.e2e.cjs` "hostile project content…": 2 injected elements without the fix, 0 with it |
| S3-2 | Low | An effect's `uid` and a diagnostic's level were interpolated into attributes unescaped (the core refuses non-UUID uids on open, but a cached local state is not re-validated) | Escaped | same scenario |
| S3-3 | Low | Roadmap links took any scheme (`javascript:`, `data:`); the data is bundled, but a link builder should not trust it | Only `https://` and repository-relative paths become links; anything else is text. Selector values are `CSS.escape`d | URL check over every roadmap URL; `test_roadmap_explorer.cjs` |
| C1 | Medium (defence in depth) | `script-src 'unsafe-inline'`: any injected markup could run script | The 200-line inline script moved to `editor_app.js`, and the one inline handler (`onsubmit`) became a listener. The core now sends `script-src 'self'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'`. The splash already had `script-src 'self'` | `test_api_security.py` `test_pages_may_run_only_scripts_from_the_studio_origin` (no inline scripts or handlers, no `eval`); the browser suite fails on any CSP violation logged to the console |
| V9 | Low | Any `https` new-window URL went to the system browser, including `user@host` URLs that disguise their destination | Only `https://github.com/…` (the only host the editor links to), with no credentials, no explicit port, at most 2 KiB | `main.rs` `only_known_https_links_reach_the_system_browser` |
| V10 | Low | At exit a hung core kept the process alive for 10 s | The exit-time stop waits 3 s (every edit is already committed atomically, so nothing is lost); the job kills the rest | reviewed; `a_hung_core_is_killed_after_the_timeout` |
| V11 | Low | `core.log` was created with default permissions (0644 on Unix) and can name projects and folders | Created and reset to 0600 on Unix. On Windows it lives in the per-user application data folder, which has a user-only ACL | `core.rs` `the_core_log_is_private` |
| V7 | — | The one-dialog guard had no test | Factored into `one_dialog` and raced from 8 threads: exactly one opens | `main.rs` `only_one_dialog_opens_even_when_requests_race` |
| PB-2 | Medium | If `quit` failed, the Preview Bridge sent SIGTERM / `TerminateProcess` to the pid the game *reported*. If the game had already exited, that pid could belong to another program | Before signalling, the bridge checks that the pid's command line still names this session's own game folder; otherwise it leaves the pid alone and says so | `test_preview_bridge.py` `test_failures_are_reported_and_the_session_still_ends` |

Remaining, accepted:
- `style-src 'unsafe-inline'`: the editor uses inline style attributes, and styles cannot run script.
- The PixelChat demo server (`pixelchat/`, a separate proof of concept, unchanged here) keeps its own CSP with
  `'unsafe-inline'`.

## Checked and sound

Navigation guard (exact `http://127.0.0.1:<port>` of this core), runtime capability scoped to that origin and the main
window, ACL on every command, empty splash capability, IPC only in the main frame, `X-Frame-Options: DENY`, literal
Host allowlist against DNS rebinding, `Origin` must match, `Sec-Fetch-Site` same-origin or none, 256-bit token compared
in constant time, strict content types forcing CORS preflight, no CORS headers, no token in URLs, logs or the window
title, handshake URL strictly validated, the reported PID never used to kill anything, stdout drained, child processes
reaped, test-only hooks compiled out of release builds, the single `unsafe` block (`MoveFileExW`) matching its
signature.
