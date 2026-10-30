# Contributing to Horizon Studio

Thanks for helping make Horizon tooling accessible to mod creators.

1. Open an issue describing a bug or proposed feature; include reproducible steps for bug reports.
2. Keep pull requests focused, with a clear explanation and tests for behavior changes.
3. Run `python -m unittest discover -s tests -v` before opening a PR.
4. Keep code identifiers, documentation, and public API text in English. Add both English and Russian translations for any new UI messages in `i18n.js`.
5. Preserve backward compatibility with `.hstudio.json` project schema 2 unless migration is explicitly implemented.
6. Do not bundle proprietary Horizon/Minecraft assets, publish credentials, or claim game compatibility without reproduction.

All contributors must follow the project's [Code of Conduct](CODE_OF_CONDUCT.md). Changes to the project are licensed under MIT.
