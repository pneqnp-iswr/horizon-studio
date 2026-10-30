# Editor ecosystem comparison: Java modding tools → Horizon → Horizon Studio

Research note for the desktop transformation (cycle 4). It asks what Java Edition modders get from their tools, what
Horizon (a Rust re-implementation of Minecraft: Java Edition) can load **today**, and therefore what Horizon Studio
may honestly offer. Engine facts are read from the Horizon source at the audited pin
[`d2186eb`](https://github.com/horizon-rust/horizon/tree/d2186eb9aa022a64a8b26e6989a04e44fba99ee7) and are encoded
in the capability registry ([`studio_core/engine_profiles.json`](../../studio_core/engine_profiles.json),
[ENGINE_CAPABILITIES.md](../ENGINE_CAPABILITIES.md)). Tool facts come from the tools' own documentation (sources at
the end). Nothing here claims that content loads or plays in the game: that is HS-002, still blocked.

## 1. What Horizon offers at `d2186eb`

From `docs/api/stability.md`, `docs/mods.md`, `docs/native-mods.md`, `docs/shaders.md` and
`crates/horizon-client/src/game/native_hooks.rs` upstream:

| Surface | Package | Version | Stability | Trust |
|---|---|---|---|---|
| Content mods: data-driven blocks and items that copy vanilla templates, plus assets and data files (recipes, loot tables, tags, structures, lang) | `.hmod` (`horizon-mod.toml`, `api = "0.2"`, capability `registries`, `side = "both"`) | content API 0.2 | **preview** | data only; unknown keys refused; files fenced to the mod's namespaces plus vanilla and `c` tags |
| Native mods: horizon-mixins bundles (HEAD, BEFORE_CALL, RETURN, MODIFY_ARG, OVERWRITE …) or the stable native hook points | `.hnmod` (`horizon-mixin.toml` + `.rs` helpers) | `NATIVE_HOOKS_API = 7`, or a pinned `horizon_revision` | **experimental** | native code with the player's rights, **not sandboxed**; launcher shows a notice and a red warning; registry reviews |
| Shader packs: WGSL sky, material and post stages | `.hshader` (`horizon-shader new/check/pack`) | shader API 0.1 per `docs/shaders.md` (the stability table still says "not started") | **experimental** | checked before it runs |
| WebAssembly code mods | — | API levels 0–7 | **removed**; such mods "need a native port" | — |
| `cargo horizon-mod` (`new`, `build`, `run`, `check`) | — | unversioned | preview | — |

Item components: an item copies its template's data components; `components` can set or remove (`!minecraft:<type>`)
any 26.3 component that a vanilla item has. Behaviour tied to a vanilla item id does not carry over (a copied trident
does not throw, horizon#3305).

## 2. The Java ecosystem, tool by tool

| Tool | What modders do with it | Model of authoring |
|---|---|---|
| **MCreator** (2026.1) | Whole mods without code: elements (blocks, items, entities, biomes, GUIs, procedures), procedures as Blockly blocks, generator plugins per loader. 2026.1 adds a **docking** workspace with a collapsible side strip (project browser, console, debugger, code viewer; plugins add docks), a flatter IDE-like look, JetBrains Mono for code, block states for Java and Bedrock scripting. | element forms → templates → generated Java/JSON per loader |
| **Blockbench** | Cuboid and mesh models, UV and per-face textures, painting, keyframe animation; `.bbmodel` JSON with a `version`, separate `groups` and `outliner` hierarchy; no formal spec (the source and examples are the reference); per-format feature flags; custom loaders via a Blockbench plugin format | direct manipulation in a 3D viewport, export per format |
| **Fabric** | Java mods on a lightweight loader with mixins and the Fabric API; datagen through providers | code |
| **NeoForge** | Java mods with events and registries; **data generation** runs providers (models, blockstates, tags, loot, recipes, lang) from a Data run configuration | code → generated JSON |
| **KubeJS** | JavaScript in `startup_scripts` (registration), `server_scripts` (recipes, tags, loot events), `client_scripts` | scripted events on a running loader |
| **CraftTweaker** | ZenScript (its own language) to add and remove recipes and tweak data in modpacks | scripted data edits |
| **GeckoLib** | Animated entities, blocks and armour from Blockbench models (GeckoLib Animation Utils plugin): model, texture, animation JSON | Blockbench → runtime animation library |

## 3. Mapping: Java concept → Horizon support → Studio model → backend → evidence

Evidence levels follow [COMPATIBILITY_EVIDENCE.md](../COMPATIBILITY_EVIDENCE.md): *unit*, *official-static* (the pinned
`cargo-horizon-mod check` accepts the package), *browser-e2e*, *game-load* (blocked, HS-002), *gameplay* (planned).

| Java concept (tool) | Horizon support at `d2186eb` | Studio authoring model | Backend | Evidence today |
|---|---|---|---|---|
| Simple block (MCreator block element; NeoForge `BlockStateProvider`) | yes: `data/<id>/horizon/block/*.json` copying a vanilla template (`registries`, API 0.2) | Block form in the inspector; template, hardness, light, sounds, tool tag | `.hmod` | official-static, browser-e2e |
| Simple item, stack size, rarity | yes: `data/<id>/horizon/item/*.json` | Item form | `.hmod` | official-static, browser-e2e |
| Item with custom damage/durability (component patch) | yes: `components` set/remove on a template | **not yet** in Studio: needs a typed component editor (HS-009 candidate) | `.hmod` | none |
| Shaped / shapeless crafting recipe (MCreator recipe; datagen `RecipeProvider`; KubeJS `event.shaped`) | yes: vanilla recipe JSON in `data/<id>/recipe/` | 3×3 grid on the canvas | `.hmod` | official-static, browser-e2e |
| Furnace, smoking, stonecutting, smithing, campfire recipes | vanilla data files are copied; not exercised by Studio | shown as **planned** stations in the UI (locked) | `.hmod` | none |
| Block drops (`LootTableProvider`) | yes: `data/<id>/loot_table/` | generated from the block form | `.hmod` | official-static |
| Tags (`TagsProvider`; KubeJS tag events) | yes: vanilla and `c` tag additions merge in load order; `replace` is logged | mining tool / tier tags from the block form | `.hmod` | official-static |
| Translations (`LanguageProvider`) | yes: `assets/<id>/lang/*.json` | EN and RU names per entry | `.hmod` | official-static |
| Structure templates (NBT) | files load; placement needs worldgen data or commands | procedural structure generator with preview | `.hmod` | official-static (files only) |
| Block/item models and textures (Blockbench cuboids) | yes: resource files copied into the resource root | Source & 3D workbench: JSON overrides, WebGL cuboid preview, PNG textures | `.hmod` | unit, browser-e2e |
| `.bbmodel` import with animations (Blockbench, GeckoLib) | static cuboid models only; no animation runtime for content mods | **planned**: import cuboids and UVs, report what is lost (animations, meshes) | `.hmod` | none |
| Custom entity (MCreator living entity; GeckoLib) | **no** content-mod registry; no verified native hook | shown as **unsupported** with the reason; data is kept | — | — |
| Procedures / event logic (MCreator procedures; KubeJS events) | only through native mods (mixins or hook points) | **planned** typed visual graph → IR → capability check → `.hnmod` generator behind a trust warning (HS-010) | `.hnmod` | none |
| Recipe viewer panel (JEI-like) | native hook API 2+: item panel and recipe pages | not planned in Studio | `.hnmod` | none |
| Shader packs (Iris/OptiFine) | Horizon's own `.hshader` (WGSL stages); Iris/OptiFine packs have a separate loader | **planned** (HS-013) | `.hshader` | none |
| Bedrock add-ons / Bedrock scripting (MCreator 2026.1) | not applicable: Horizon is Java Edition | none | — | — |
| WebAssembly mods | **removed** | none; Studio never offers it | — | — |

## 4. What this means for Horizon Studio

1. **Lead with what is real.** Content mods (API 0.2, preview) are the only surface with official-static evidence.
   The editor makes them first-class and keeps every other surface visible but locked, with the reason and the
   required API taken from the registry. The in-app *Development journey* says which is which.
2. **Borrow the workbench, not the scope.** MCreator 2026.1 and Blockbench converge on an IDE layout: docked side
   strip, project browser, central canvas, properties, console. Studio adopts that information architecture
   (top bar, activity rail, explorer, canvas, inspector, output, status bar) without claiming MCreator's breadth.
3. **Data generation is the backend model.** NeoForge datagen and Studio share the idea that people author
   high-level objects and a generator writes the JSON. Studio's generator already produces byte-identical,
   officially checked packages; new kinds join through the canonical document (`studio.project/1`) and the registry.
4. **Code features go native and stay warned.** KubeJS-style logic has no content-mod equivalent; the only route is
   `.hnmod`, which runs unsandboxed. Studio may generate it only behind an explicit, separate trust step, never
   silently, and never in the application's own process.
5. **Interchange with Blockbench, honestly.** Import `.bbmodel` cuboids and UVs with a loss report (animations,
   meshes, locators), since the format has no formal specification and Horizon content mods have no animation
   runtime.

## Sources

- Horizon at `d2186eb`: `docs/api/stability.md`, `docs/mods.md`, `docs/native-mods.md`, `docs/shaders.md`,
  `crates/horizon-client/src/game/native_hooks.rs` (read from the pinned checkout).
- [MCreator 2026.1 – Biggest mod making update so far](https://mcreator.net/news/122261/mcreator-20261-biggest-update-history-minecraft-mod-making)
- [The .bbmodel format (Blockbench wiki)](https://blockbench.net/wiki/docs/bbmodel), [Blockbench format features](https://www.blockbench.net/wiki/blockbench/formats)
- [NeoForge documentation: resources and data generation](https://docs.neoforged.net/docs/resources)
- [GeckoLib wiki: Making your models (Blockbench)](https://github.com/bernie-g/geckolib/wiki/Making-Your-Models-(Blockbench))
- [CraftTweaker documentation](https://docs.blamejared.com/)
- KubeJS documentation (mods.latvian.dev/kubejs): script folders and recipe events
