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
| Observe | A PNG of the next presented frame, written by the game into the session folder (never a caller's path) and copied out only if it is a valid PNG; the player's state | `screenshot PATH`, `state` |
| Confirm the content | The strict check below (PB-001): the game itself confirms the package's items | `give ITEM 1`, `inventory` |
| End | Save and quit; if that fails, the game's process is stopped. Ending twice is harmless | `quit` |
| Record | `horizon-studio.preview-evidence/1` (below) | — |

## Confirming content (PB-001)

The first version looked for the item id anywhere in the text of the `inventory` reply. That is a false positive
waiting to happen: `ruby_demo:ruby` is a substring of `ruby_demo:ruby_block`, an id can appear inside another
stack's components, and `give` answers `{"ok": true}` without the item having arrived. In single player, `give` runs
`give @s` on the integrated server and reports the requested count, not what reached the inventory
(`crates/horizon-client/src/game/control.rs` at `3c1d4b39`).

The check now follows the inventory schema upstream actually returns. That schema is `inventory_value` in
`crates/horizon-client/src/game/agent.rs`: hotbar slots 0–8, main 9–35, armor 500–503, offhand 504, the carried stack,
and `counts`.

1. **Only the package's items.** The ids come from the package itself: `assets/<mod>/items/*.json` and
   `data/<mod>/horizon/item/*.json`. A vanilla item, or anything else the package does not define, is never checked,
   because confirming `minecraft:diamond` says nothing about a mod.
2. **A control item.** `<mod>:studio_absent_<session>` must be refused by `give`. A game (or a stand-in) that accepts
   ids no package defines confirms nothing.
3. **Before, give, after.** The inventory is read, one item is given, and the inventory is read again. It is polled
   for up to 5 s, because the server's update reaches the client later. The check requires exactly one more of that
   exact id in real slots.
4. **Strict replies.** The groups must have the right number of slots, each in its place, with no duplicates; ids must
   be namespaced and counts positive integers; the game's `counts` must equal the slot totals. Anything else is
   `MALFORMED_INVENTORY`, `AMBIGUOUS_INVENTORY` or `MALFORMED_REPLY`, and confirms nothing.
5. **Each item is recorded:** before, after, the slots it is in, `give`'s reply (kept for the record, never trusted),
   and a reason when it is not confirmed (`NOT_IN_PACKAGE`, `NOT_IN_INVENTORY`, `WRONG_QUANTITY`, …).

The stand-ins in `tests/fakes/` speak the same schema and can be told to lie (`FAKE_CTL_MODE`):
- give succeeding with nothing added;
- the id inside another stack's components;
- a prefixed id or two items;
- a late update;
- 8 hotbar slots or a duplicate slot;
- mismatched counts, or a list instead of an object;
- accepting any id.

`tests/test_preview_bridge.py` checks that none of these reaches `game-load`, and that the honest stand-in does.

## What the evidence may claim

- **Levels:**
  - `launched`: the game started with the package and drew a frame.
  - `game-load`: in addition, the game confirmed every listed project item.
- **A screenshot alone is never `game-load`:** the evidence says so in its notes.
- **Not verified:** gameplay, events and multiplayer. Each record says that too.
- **Binding:** every record carries the package's SHA-256, the Horizon build the game reported, the Launch API, the
  session id, the world and the seed, plus a SHA-256 `digest` over the binding, the level and the content checks.
- **What `game-load` needs:**
  - confirmed content (above);
  - a known game build and Launch API;
  - a package unchanged since the session started; a package edited during the session is reported and downgraded.
- **Contents:** the session folders, the screenshot's SHA-256, a state summary and the list of commands with their exit
  codes.

## Safety

- **Installation:** only one the person already has. Studio never downloads game files, never sees an account or a
  session, and does not bypass the official launcher's ownership gate (`docs/api/launch.md`: start Horizon only for a
  player who owns Minecraft: Java Edition).
- **Worlds:** personal worlds are never opened or modified; every session gets new folders.
- **Content:** only content packages go in. Native mods (`.hnmod`) are out of scope here and need HS-010's isolated
  build and explicit approval of Horizon's native-code trust boundary.
- **Cleanup:**
  - a failed launch, a timeout or a failed step still ends the session;
  - one session runs at a time (`SESSION_ACTIVE`);
  - a failed screenshot leaves no partial file;
  - the evidence JSON is written atomically.
- **Process ownership:** if `quit` fails, the game's process is stopped only while its command line still names this
  session's own game folder. A process id that has gone or been reused by another program is never signalled.
- **Version check:** a `--launch-api` reply that is not a JSON object, has no option list, times out or exits with an
  error means Studio does not start the game.

## Status

`partial`. It is tested against stand-ins that speak `horizon-ctl`'s command line and replies
(`tests/fakes/`, `tests/test_preview_bridge.py`): isolation, refusals, failures and the evidence levels. **No real
Horizon client has been driven by it yet.** That needs an authorized installation, the same blocker as HS-002. Until
then its validation target, `game-load`, is not reached.

```sh
python horizon_cli.py preview project.hstudio.json --ctl ~/horizon/horizon-ctl --yes -o preview.json   # checks every package item
python horizon_cli.py preview project.hstudio.json --ctl ~/horizon/horizon-ctl --yes --item ruby_demo:ruby -o preview.json
```
