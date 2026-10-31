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
