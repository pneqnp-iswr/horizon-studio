# Horizon Studio — Master Roadmap

Source-audited baseline dated **2026-10-30**. Current focus: **Horizon Studio only**; no changes to the companion fork.

## Deliverables

- [Full Master Engineering Roadmap (Markdown)](master-2026-10-30.md) — verified code baseline, 24 sections, competitive matrix, 8 demo projects, detailed stages, backlog and three initial iterations.
- [PDF (generated in CI)](master-2026-10-30.pdf) — printable report; workflow also stores an Actions artifact.
- [Print-ready HTML source](master-2026-10-30.html) — stable reproducible PDF input and browser-readable version.
- [Original master research brief](research-brief-2026-10-30.md) — full original requirements and acceptance criteria.
- [Legal and distribution policy](LEGAL_AND_DISTRIBUTION.md).

## First engineering milestones

1. P0: secure localhost HTTP/POST API and add adversarial tests.
2. P0: version-pinned official `cargo horizon-mod check` plus controlled in-game integration tests.
3. P1: versioned project workspaces, transactional persistence and migrations.
4. P1: robust command/undo model, modular UI, asset pipeline and browser tests.
5. P1: typed gameplay IR, capability registry and independent export adapters.

The report is a static source/API audit. CI-reported success is not equivalent to a verified game session. Benchmark figures are proposals unless marked source-verified.

Minecraft is a trademark of Mojang/Microsoft. Horizon Studio is unofficial and is not approved by or associated with Mojang or Microsoft.
