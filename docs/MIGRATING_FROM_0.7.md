# Moving from the 0.7 EXE to the desktop app

*Русская версия ниже.*

Horizon Studio 0.7 was one Windows executable that opened the editor in your browser. The desktop app is a window of
its own: an installer (`…-setup.exe`) or a portable folder in a ZIP. Your projects come with you unchanged; this page
says exactly what moves, what does not, and how to check.

## What stays exactly the same

These are tested against real files written by the v0.7.0 core (`tests/test_migration_0_7.py`, fixtures in
`tests/fixtures/legacy_0_7/`):

- **Project files.** A `.hstudio.json` saved by 0.7 opens unchanged, and saving it again gives the same bytes.
- **Packages.** The same project builds a byte-identical `.hmod`, for both fixture projects.
- **Disk workspaces.** 0.7's autosave in `%USERPROFILE%\.horizon-studio\workspaces` (or `~/.horizon-studio/workspaces`)
  is found under the same revision when you open the project or type its mod ID.

## What is different

- **Your browser tab's own copy does not move.** 0.7 kept the last state in the browser's storage for
  `http://127.0.0.1:8787`; the desktop app is a different window and origin. The disk workspace and your saved files do
  move.
- **Undo history is new.** It is now kept on disk next to the workspace and survives restarts (HS-020); it starts
  empty for projects from 0.7, and your first edit is an ordinary undoable step.
- **The portable build is a folder.** `HorizonStudio.exe` needs the `core\` folder next to it: extract the whole ZIP.
  It is not a single-file executable.
- **New:** the AI Creator (the fixture provider is labelled as simulated; Claude only with your key and consent), and
  VFX Studio emitters. Both are optional.

## Settings, backups and data locations

| What | 0.7 EXE | Desktop app |
|---|---|---|
| Projects you saved | wherever you saved them | the same files; open them with *Open project* |
| Autosaved workspaces | `~/.horizon-studio/workspaces` | the same folder, plus one `*.journal.json` per project holding the undo history |
| AI settings (offline mode, consent, model) | — | `~/.horizon-studio/ai-settings.json` (no secrets) |
| API keys | — | only in the system credential store (Windows Credential Manager), never in a file |
| Language and the last opened project | the browser's storage for `127.0.0.1:8787` | the app window's storage: **not remembered between launches yet** (see limitations) |

- **Backup.** Copy your saved `.hstudio.json` files. To keep the autosaves too, copy `~/.horizon-studio/workspaces`.
  Each workspace also keeps its previous good version (`*.previous`), which Studio uses automatically if the current
  one is damaged.
- **Recovery.** If the app or the computer stops mid-save, the workspace is either the old version or the new one,
  never a mix. A damaged current copy falls back to the previous one, and the editor says so. A damaged history file
  is reset; the project is kept.

## Upgrading, parallel installations and rollback

- **Parallel installations.** The 0.7 EXE and the desktop app can be installed and run side by side; see the end of
  this section.
- **Upgrading.** Later installers install over this one. Your data lives in `~/.horizon-studio`, not in the program
  folder or the app's own AppData folders, so uninstalling removes the program but not your projects, workspaces or
  settings. CI checks that the uninstaller removes the program; it does not yet check that `~/.horizon-studio` is left
  in place.
- **Rolling back to 0.7 is safe for your files.** This was tested with the real 0.7.0 code: it opens a project saved by
  the desktop app (with an effect, an engine target, plugin data and extensions) and saves it back byte for byte. It
  keeps what it does not understand untouched, but it cannot edit effects. Older releases stay downloadable on the
  releases page.
- **File associations.** Not set up: double-clicking a `.hstudio.json` file does not open Studio. Use *Open project*.

## Known limitations

- **Settings between launches.** The desktop app does not yet remember the language and the last opened project
  between launches, because its core uses a new local port each time. Your project is safe in the disk workspace:
  open it, or type its mod ID and choose *Restore disk*.
- **Unsigned.** SmartScreen warns on first launch ([SIGNING.md](SIGNING.md)).
- **No in-game verification.** Loading Studio mods in the Horizon game has not been verified (HS-002).

## Steps

1. **In 0.7:** *Save project* to get a `.hstudio.json` backup (recommended, even though the disk workspace moves too).
2. **Install** the desktop app (per user, no administrator rights), or extract the portable ZIP anywhere.
3. **Open** your saved project, or type its mod ID. If the editor and the disk copy differ, Studio asks you to choose:
   *Restore disk* or *Keep editor*. Nothing is overwritten silently.
4. **Remove 0.7** when you are done: it is a single file, so delete `HorizonStudio-0.7.0-Windows-x64.exe`.

Running both at the same time is safe. They share the workspace folder, and every write names the revision it expects,
so one cannot overwrite the other silently. If 0.7 changes a project after the desktop app did, the desktop app keeps
the document and starts its history again, and says so.

## Checking a download

Each release lists SHA-256 checksums in `SHA256SUMS.txt` and in `desktop-manifest.json`:

```powershell
Get-FileHash .\HorizonStudio-<version>-Windows-x64-setup.exe -Algorithm SHA256
```

Whether a build is signed is stated in the release notes and the manifest, from the actual Authenticode check
([SIGNING.md](SIGNING.md)). An unsigned build makes Windows SmartScreen warn; that warning is expected for unsigned
builds.

---

# Переход с EXE 0.7 на настольное приложение

Horizon Studio 0.7 был одним исполняемым файлом Windows, который открывал редактор в браузере. Настольное приложение —
отдельное окно: установщик (`…-setup.exe`) или переносимая папка в ZIP. Проекты переходят без изменений.

- **Не меняется.** Проверено на настоящих файлах, записанных ядром v0.7.0:
  - файлы `.hstudio.json` открываются и сохраняются байт в байт;
  - `.hmod` собирается побайтно тем же;
  - автосохранение в `~/.horizon-studio/workspaces` находится под той же ревизией.
- **Меняется.**
  - Копия в хранилище браузера не переносится: другое окно и origin. Переносятся рабочее пространство на диске и
    сохранённые файлы.
  - История отмены теперь на диске и переживает перезапуск; для проектов из 0.7 она начинается пустой.
  - Переносимая версия — папка: `HorizonStudio.exe` нужна папка `core\` рядом. Это не один файл.
- **Шаги.**
  1. В 0.7 — *Сохранить проект*.
  2. Установить приложение или распаковать ZIP.
  3. Открыть проект или ввести его ID мода. При расхождении Studio спросит: *Восстановить с диска* или *Оставить
     редактор*.
  4. Удалить файл 0.7.
- **Обе версии одновременно — безопасно:** каждая запись проверяет ревизию.
- **Подпись** указана в примечаниях к выпуску и в манифесте по результатам реальной проверки Authenticode
  ([SIGNING.md](SIGNING.md)).
- **Данные и резервные копии.**
  - Проекты, рабочие пространства (`~/.horizon-studio/workspaces`, рядом журналы истории `*.journal.json` и
    предыдущие версии `*.previous`) и настройки ИИ хранятся вне папки программы.
  - Удаление программы их не трогает.
  - Ключи API хранятся только в системном хранилище учётных данных.
- **Откат на 0.7 безопасен для файлов.** Проверено настоящим кодом 0.7.0: он открывает проект настольной версии (с
  эффектом, целевым движком и данными плагинов) и сохраняет его байт в байт. Непонятное он не трогает, но эффекты
  редактировать не может.
- **Ассоциации файлов** не настроены: открывайте проекты через *Открыть проект*.
- **Ограничение.** Язык и последний открытый проект пока не запоминаются между запусками настольной версии: её ядро
  каждый раз получает новый локальный порт. Проект при этом сохранён на диске: откройте его или введите ID мода и
  выберите *Восстановить с диска*.
