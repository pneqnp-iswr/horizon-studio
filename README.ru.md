<p align="center">
  <img src="docs/banner.svg" alt="Баннер Horizon Studio" width="100%" />
</p>

<h1 align="center">Horizon Studio</h1>
<p align="center"><strong>Визуальный набор инструментов для создания модов Horizon</strong><br/>Локальный редактор, экспериментальная упаковка <code>.hmod</code>, процедурные структуры, диагностика и CLI для разработчиков.</p>

<p align="center">
  <a href="README.md">English version</a> ·
  <a href="CHANGELOG.md">Changelog</a> ·
  <a href="CONTRIBUTING.md">Contributing</a> ·
  <a href="SECURITY.md">Security</a>
</p>

> **Важно:** Horizon Studio — **неофициальный** open-source проект. Он **не связан** с Mojang, Microsoft или разработчиками Horizon. В репозиторий не входят проприетарные игровые файлы, обходы аутентификации и оригинальные игровые ассеты.

## Что это такое

Horizon Studio — локальный тулкит для создания и упаковки контентных модов для Horizon без необходимости вручную писать все JSON/NBT-файлы или сразу лезть в код на Rust.

Версия **0.6 — Source Workbench** добавляет проверяемое редактирование JSON, локальный 3D-просмотр моделей и импорт ресурсов из выбранного пользователем архива.

## Главное в версии 0.6

### Новый редактор исходников и просмотр
- Source Workbench: безопасные JSON-изменения с проверкой перед экспортом.
- WebGL-просмотр кубических моделей с программным резервным режимом.
- Выборочный импорт текстур из локального пользовательского ZIP/JAR без распространения игровых ассетов.

### Интерфейс Recipe Lab
- новый вид **галереи рецептов**
- новая структура **left rail + explorer + workspace**
- более профессиональная подача проекта для GitHub
- английский по умолчанию, русский переключатель сохранён

### Сохранённые возможности
- создание **блоков** и **предметов** на основе ванильных шаблонов
- **shaped** и **shapeless** рецепты
- пользовательские **PNG-текстуры**
- двуязычные названия `en_us` и `ru_ru`
- генерация тегов инструментов добычи и минимального тира
- **Voxel Architect** с шестью генераторами структур
- поворот и зеркалирование экспортируемых структур
- **Mod Doctor** для статической диагностики
- **CLI** для автоматизации сборки, проверки и инспекции

## Быстрый запуск

Нужен **Python 3.11+**.

### Запуск редактора

**Windows**
```bat
start_windows.bat
```

**Linux / macOS**
```sh
./start_linux_macos.sh
# или
python3 studio.py
```

Открой:
```text
http://127.0.0.1:8787
```

## CLI

```sh
python horizon_cli.py doctor examples/workshop_showcase.hstudio.json
python horizon_cli.py inspect examples/workshop_showcase.hstudio.json
python horizon_cli.py build examples/workshop_showcase.hstudio.json --output dist/workshop_showcase.hmod
python horizon_cli.py source examples/workshop_showcase.hstudio.json --output dist/workshop_showcase-source.zip
```

## Тесты

```sh
python -m unittest discover -s tests -v
```

Актуальные результаты доступны в GitHub Actions: полный набор тестов запускается на Python 3.11/3.12 в Windows и Ubuntu.

## Структура проекта

```text
index.html           Интерфейс редактора
studio.py            Локальный HTTP-сервер и экспорт API
i18n.js              Локализация EN/RU
voxel_architect.py   Детерминированный генератор структур
mod_doctor.py        Статическая диагностика
horizon_cli.py       CLI для build / inspect / doctor
examples/            Примеры
tests/               Набор тестов
```

## Ограничения

### Чего проект пока не делает
- не подтверждает совместимость с игрой без реального запуска
- не подтверждает официальный формат без `cargo horizon-mod check`
- не реализует произвольную игровую логику через content-only упаковку
- не включает оригинальные игровые ассеты

### Что позже может потребовать более глубокую Rust / engine-интеграцию
- native hooks
- поведенческие системы сервера
- runtime логики и событий
- визуальный граф игровых механик в стиле MCreator

## Лицензия

MIT.

## Дальнейшие идеи

- больше типов верстаков/станций
- браузер текстур и иконок
- улучшенный импорт ассетов
- визуальный редактор логики для будущих native-расширений
- оформленные GitHub Releases
- реальные скриншоты и фирменные баннеры

Этот README специально подготовлен так, чтобы его было легко дальше продолжать вручную: добавить баннеры, скриншоты, badges, roadmap и ссылки на релизы.

## Скачать `.exe` по версиям

[**Открыть GitHub Releases — версии для Windows**](https://github.com/pneqnp-iswr/horizon-studio/releases)

Каждая опубликованная версия (например, `v0.6.0`) содержит свой файл `HorizonStudio-<версия>-Windows-x64.exe` и контрольную сумму `SHA256SUMS.txt`.

**Python не нужен:** запусти `.exe` на Windows 10/11 x64, нажми **Open Studio**, а для остановки — **Stop & Exit**. Программа использует локальный адрес `127.0.0.1:8787`. Это переносимая программа, не установщик. Исполняемый файл пока не подписан цифровой подписью — Windows SmartScreen может показать предупреждение.

После изменения файла `VERSION` в ветке `master` GitHub Actions запускает Windows-сборку, тестирует реальный `.exe` и публикует новую версию в GitHub Releases. Уже выпущенные версии не перезаписываются.
