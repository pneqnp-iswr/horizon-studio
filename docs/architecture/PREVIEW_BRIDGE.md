# Preview Bridge (HS-023)

Puts a Studio project into a real Horizon client and records what that proves. It drives upstream's own agent-control
tool, `horizon-ctl`, which ships beside the game (engine contract `game.agent_control`, audited at Horizon `3c1d4b39`).
It works without AI: `horizon_cli.py preview` uses it today, and the AI Creator's live loop (HS-024) will use the same
class (`studio_core/preview_bridge.py`).

## A session

| Step | What happens | Upstream interface |
|---|---|---|
| Discover | The `--ctl` path, else `HORIZON_CTL`, else `PATH`; the game must be beside it | `horizon-ctl` ships beside `horizon-client` |
| Check the version | The game's Launch API must be `0.x` (at least `0.1.0`) and offer `--game-dir` and `--home`; otherwise Studio refuses to start it | `horizon-client --launch-api` (`docs/api/launch-reference.md`) |
| Approve | Nothing starts without the person's approval of this session (`--yes` in the CLI) | — |
| Isolate | A fresh `~/.horizon-studio/preview/<id>/game` (saves, options) and `…/home` (logs, crash reports), a private control socket, and a new world `StudioPreview` with a chosen seed | `--game-dir`, `--home`, `horizon-ctl --socket`, `launch --world --seed` |
| Load the project | The Studio `.hmod` (content only, no code) as a development mod; rendered offscreen | `--dev-mod PATH`, `--offscreen` |
| Wait | Until the world is loaded | `wait-for loaded --timeout` |
| Observe | A PNG of the next presented frame; the player's state | `screenshot PATH`, `state` |
| Confirm the content | Give one of the project's items and look for it in the inventory: the game itself confirms the mod's content exists | `give ITEM 1`, `inventory` |
| End | Save and quit; if that fails, the game's process is stopped. Ending twice is harmless | `quit` |
| Record | `horizon-studio.preview-evidence/1` (below) | — |

## What the evidence may claim

- **Levels:**
  - `launched`: the game started with the package and drew a frame.
  - `game-load`: in addition, the game confirmed every listed project item.
- **A screenshot alone is never `game-load`:** the evidence says so in its notes.
- **Not verified:** gameplay, events and multiplayer. Each record says that too.
- **Contents:** the package's SHA-256, the Launch API and Horizon versions, the session folders, the seed, the
  screenshot's SHA-256, a state summary and the list of commands with their exit codes.

## Safety

- **Installation:** only one the person already has. Studio never downloads game files, never sees an account or a
  session, and does not bypass the official launcher's ownership gate (`docs/api/launch.md`: start Horizon only for a
  player who owns Minecraft: Java Edition).
- **Worlds:** personal worlds are never opened or modified; every session gets new folders.
- **Content:** only content packages go in. Native mods (`.hnmod`) are out of scope here and need HS-010's isolated
  build and explicit approval of Horizon's native-code trust boundary.
- **Cleanup:** a failed launch, a timeout or a failed step still ends the session.

## Status

`partial`. It is tested against stand-ins that speak `horizon-ctl`'s command line and replies
(`tests/fakes/`, `tests/test_preview_bridge.py`): isolation, refusals, failures and the evidence levels. **No real
Horizon client has been driven by it yet.** That needs an authorized installation, the same blocker as HS-002. Until
then its validation target, `game-load`, is not reached.

```sh
python horizon_cli.py preview project.hstudio.json --ctl ~/horizon/horizon-ctl --yes --item ruby_demo:ruby -o preview.json
```
