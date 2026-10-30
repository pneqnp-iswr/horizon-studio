# Legal, licensing, and distribution policy

Updated: 2026-10-30. Engineering policy, not a legal opinion or guarantee. Any distribution involving Minecraft entitlement or ownership requires jurisdiction-specific legal review.

## Horizon Studio — acceptable engineering scope

- Develop and publish original Studio source code, original sample models, original artwork, our own documentation and authoring tools, subject to their licenses.
- Studio is currently MIT-licensed. Keep applicable license and attribution notices for all third-party code, upstream Horizon components and dependences.
- Build content `.hmod` packages of original or appropriately licensed assets. Require pinned official validation and game-load evidence before calling them compatible.
- User-supplied resource packs may be processed locally for lawful use; do not redistribute their proprietary contents in the Studio repo, releases or samples.
- Use only fonts, icons, textures and model packs with verified redistribution rights. A Minecraft-like design does not give permission to bundle Minecraft's actual assets.
- Identify Studio as an unofficial independent project, not approved by or associated with Mojang or Microsoft.

## Restrictions

- Do not distribute Minecraft clients, servers, jars, proprietary game textures, sounds, shaders, skins or derivatives without necessary permission.
- Do not provide authorization or ownership-bypass workflows as a substitute for entitlement to paid game software or content.
- Do not present an offline nickname, third-party launcher or open-source Rust engine as proof that someone has a Minecraft license.
- Do not silently execute user-supplied native `.hnmod` Rust code. Native mods have full OS-level permissions and are not sandboxed.
- Do not publish third-party code, fonts, graphics or samples without attribution and license verification.

## Separate companion fork

The `pneqnp-iswr/unlicensed-horizon` fork is OUT OF SCOPE for the current Studio engineering work. Its launcher and distribution flows need their own analysis. An independently written tool for authorized users has a different legal risk profile than distributing proprietary games or circumventing account/ownership checks. Another product's existence, including TLauncher, is not a legal precedent.

## Primary sources

1. [Minecraft EULA](https://www.minecraft.net/en-us/eula)
2. [Minecraft Usage Guidelines](https://www.minecraft.net/en-us/usage-guidelines)
3. [Horizon upstream license](https://github.com/horizon-rust/horizon/blob/main/LICENSE)
4. [Horizon native mod trust documentation](https://github.com/horizon-rust/horizon/blob/main/docs/native-mods.md)
5. [Horizon Studio license](../../LICENSE)

The EULA and usage guidelines may change. Recheck them before releases. This document does not decide all jurisdiction-dependent legal questions.
