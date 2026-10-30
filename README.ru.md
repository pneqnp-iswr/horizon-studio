# Horizon Studio

**Открытый офлайн-конструктор контент-модов для Horizon.**

[English documentation](README.md) · [Техническая матрица](docs/FEATURE_MATRIX.md) · [История изменений](CHANGELOG.md)

Horizon Studio 0.4 — **Mod Workshop** — включает визуальный редактор блоков и предметов, генератор процедурных структур, диагностику модов и консольную сборку для разработчиков.

> **Альфа-версия.** Автоматические Python-тесты, проверка HTTP API и локальные браузерные сценарии пройдены. Но готовые `.hmod` ещё **не проверены официальным `cargo horizon-mod check` и не запускались в настоящей игре Horizon**. Текущая документация Horizon описывает контент-моды прежде всего для одиночной игры.

![Фактический интерфейс версии 0.4](docs/editor-en.png)

## Возможности 0.4

- **Блоки и предметы:** ванильные шаблоны, прочность, свет, звуки, трение, редкость, размер стака и свои PNG-текстуры.
- **Инструменты добычи:** теги для кирки, топора, лопаты, мотыги; уровни камень/железо/алмаз. Игровое поведение всё ещё следует проверять в Horizon.
- **Два языка игровых названий:** `en_us` и `ru_ru` с английским резервным вариантом.
- **Крафт:** рецепты shaped/shapeless с ингредиентами из созданных модом предметов.
- **Voxel Architect:** купол, спиральная башня, лабиринт, парящий остров, кристальная роща и боевая арена. Шесть палитр, воспроизводимый seed, экспортный поворот и зеркалирование.
- **3D-просмотр:** изометрия, вращение камеры, разрезы по Y и статистика.
- **Файлы NBT:** реальные gzip-сжатые шаблоны в `data/<id>/structure/*.nbt` внутри `.hmod`.
- **Mod Doctor:** проверка структуры проекта, конфликтов рецептов и невозможных только по крафту цепочек получения. Это не официальная проверка игры.
- **CLI:** локальные сборки и диагностика без браузера, пригодные для скриптов и CI.
- **Интерфейс:** английский по умолчанию, русский через 🇬🇧 EN / 🇷🇺 RU с сохранением выбора.

## Запуск

Нужен **Python 3.11+**, сторонние библиотеки не требуются.

- Windows: `start_windows.bat`
- Linux/macOS: `./start_linux_macos.sh` или `python3 studio.py`

Открой `http://127.0.0.1:8787`. Сервер слушает только локальный адрес, в облако ничего не отправляет. Сохраняй проекты в `.hstudio.json` перед очисткой данных браузера.

## Консольная сборка

```sh
python horizon_cli.py doctor examples/workshop_showcase.hstudio.json
python horizon_cli.py inspect examples/workshop_showcase.hstudio.json
python horizon_cli.py build examples/workshop_showcase.hstudio.json -o dist/workshop_showcase.hmod
python horizon_cli.py source examples/workshop_showcase.hstudio.json -o dist/workshop_showcase-source.zip
python -m unittest discover -s tests -v
```

После сборки `.hmod` отдельно запусти официальный валидатор:

```sh
cargo install --git https://github.com/horizon-rust/horizon cargo-horizon-mod
cargo horizon-mod check dist/workshop_showcase.hmod
```

[Актуальная документация Horizon](https://playhorizon.dev/docs/content-mods).

## Ограничения

- NBT-шаблоны не размещаются в мире автоматически: нужны команды или правила генерации.
- Для новых игровых действий, событий сервера или вмешательства в движок потребуется проверенный native/server API Horizon либо отдельный патч.
- Это не функции, «невозможные на Java». Формулировка **Rust engine integration** означает зависимость от конкретного Rust-движка Horizon.
- Бинарники Minecraft, сторонние игровые ассеты и средства обхода авторизации не распространяются.

Пример `examples/workshop_showcase.hstudio.json` содержит все шесть видов построек, языковые названия и инструменты добычи. Код проекта открыт под MIT; проект не аффилирован с Horizon, Mojang или Microsoft.
