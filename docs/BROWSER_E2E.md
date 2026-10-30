# Browser end-to-end tests (HS-007)

`tests/e2e/editor.e2e.cjs` drives the real editor in Chromium against a real local Studio server. Each test starts its own `python studio.py 0` on a free loopback port with a fresh temporary `HOME`, so disk workspaces are isolated and the developer's own `~/.horizon-studio` is never touched.

## Running

```sh
# once: the Playwright library and its Chromium (CI pins playwright@1.63.0)
npm install --no-save --no-package-lock playwright@1.63.0
npx playwright install chromium

node --test --test-reporter=spec tests/e2e/*.e2e.cjs
```

Set `PYTHON` to choose the interpreter that runs `studio.py` (default `python3`, `python` on Windows).

## What is covered

| Scenario | Checks |
|---|---|
| Startup | English by default, no JavaScript errors, demo project loads with UUIDs on every object |
| Create / edit / rename | Renaming an item keeps its `uid`; recipes follow the rename; **Save project** downloads `studio.project/1` whose recipe references point at the same `uid`; new objects get UUIDv4 |
| Undo / Redo | Buttons and Ctrl+Z / Ctrl+Shift+Z; shortcuts are ignored while typing in a text field |
| Autosave and recovery | The disk workspace file under the test `HOME` contains the edit; a fresh browser profile restores it via **Restore disk** with the same `uid`s |
| Revision conflicts | A stale tab gets HTTP 409 and the conflict choice instead of overwriting another tab's newer work; **Keep editor** then overwrites explicitly |
| Legacy projects | A schema-4 example opens with the migration notice; a corrupt file is rejected and the current project stays loaded |
| Localization | Russian switch, translated workspace status, choice kept after reload |
| Source Workbench | Unique file labels; invalid JSON is refused; a valid override is applied, appears in the exported `.hmod`, and Undo removes it |
| Export | The unedited demo exports exactly the `.hmod` bytes the official checker accepted (SHA-256 `ee3e1c87…`) |
| Error states | An invalid mod ID pauses disk autosave and makes export fail with a visible message and no download |
| Small screens | 1280×720, 1024×640 and 390×844: project controls are reachable (drawer on narrow windows, Escape closes it and returns focus), the Configure button is not covered, no horizontal scrolling |

Any uncaught page error, console error, failed static asset request or HTTP 5xx fails the test. Expected API answers (404 "no workspace yet", 409 conflict, 400 validation) are part of the protocol and each test asserts how the UI handles them.

## Failure artifacts

On failure the harness writes a full-page screenshot, a Playwright trace (`npx playwright show-trace <file>`) and the server log to `test-results/e2e/`; CI uploads them as the `browser-e2e-failures` artifact for 14 days. They contain only the synthetic demo projects created by the tests.

## Limits

- Chromium on Ubuntu only; Firefox, WebKit and Windows browsers are not exercised yet.
- The Windows executable is not driven by these tests (its own smoke test fetches the editor and its scripts).
- Nothing here starts the Horizon game: browser E2E is evidence about the editor, not about game compatibility.
