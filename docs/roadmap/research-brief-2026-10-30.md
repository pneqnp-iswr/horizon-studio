# MASTER RESEARCH PROMPT — HORIZON STUDIO ULTIMATE ROADMAP

## Роль и уровень экспертизы

Ты выступаешь в роли международной исследовательской и инженерной команды, разрабатывающей техническую стратегию для **Horizon Studio** — будущей универсальной среды создания модификаций, игрового контента и расширений движка Minecraft Horizon, написанного на Rust.

Представь, что над проектом работают:

1. Principal Software Architect — архитектура IDE, расширяемость, техническая стратегия.
2. Senior Rust Engine Engineer — Rust, ECS, игровые движки, runtime, ABI, сборка.
3. Minecraft Modding Expert — MCreator, Forge, Fabric, NeoForge, Blockbench, GeckoLib и экосистема модификаций.
4. Graphics & Rendering Engineer — wgpu, WebGPU, WGSL, PBR, shaders, VFX.
5. Physics Simulation Engineer — игровая физика, транспорт, разрушения, симуляции.
6. AI & NPC Systems Researcher — Behavior Trees, GOAP, Utility AI, навигация, LLM-NPC.
7. IDE & Developer Tools Engineer — Monaco, LSP, Cargo, компиляторы, code generation, debugging.
8. Senior UX/UI Designer — профессиональные creative tools, дизайн-системы, удобство длительной работы.
9. Technical Artist — Blockbench, 3D-модели, анимации, текстуры, эффекты.
10. QA & Release Engineer — автотесты, CI/CD, GitHub Releases, совместимость, производительность.
11. Security Architect — изоляция модов, пользовательский код, sandbox, разрешения.
12. Open-Source Project Lead — документация, контрибьюторы, лицензирование, развитие сообщества.

Не разыгрывай вымышленный диалог между специалистами. Объедини их компетенции в одном технически последовательном исследовании.

**Твоя задача — разработать максимально глубокий, проверяемый, практически исполнимый и технически профессиональный roadmap развития Horizon Studio из актуального состояния в универсальную игровую среду разработки.**

---

# 1. Проект и исходные репозитории

Основной проект:

https://github.com/pneqnp-iswr/horizon-studio

Связанный форк игрового движка:

https://github.com/pneqnp-iswr/unlicensed-horizon

Оригинальный Horizon:

https://github.com/horizon-rust/horizon

Официальная документация:

https://playhorizon.dev/docs/

В качестве стартового ориентира используй Horizon Studio v0.6.0, но обязательно проверь, является ли она последней на момент исследования.

Выполни настоящий аудит GitHub, а не пересказывай README.

Изучи:

- Все основные директории и исходные файлы.
- Реальную функциональность редактора.
- Python backend и локальные HTTP API.
- HTML, JavaScript и систему интерфейса.
- Source Workbench.
- 3D Model Viewer.
- Voxel Architect.
- Mod Doctor.
- Систему локализации EN/RU.
- Импорт ресурсов и текстур.
- CLI и экспорт модификаций.
- Windows launcher и PyInstaller.
- GitHub Actions и релизы.
- Тестовое покрытие.
- Технический долг.
- Безопасность пользовательских данных.
- Реальную совместимость с Horizon.

Зафиксируй точные commit SHA, дату проверки и версии.

Для каждой существующей функции укажи один из статусов:

- Verified and working.
- Implemented but insufficiently tested.
- Experimental.
- Incomplete.
- Broken.
- Planned.
- Unsupported by current engine.

Нельзя объявлять функцию работающей только потому, что она присутствует в README или UI.

Отдельно проверь историю и актуальный контракт `.hmod`, `.hnmod`, WebAssembly-компонентов, `horizon-mixins`, серверных API и механизмов запуска модов.

Если разные страницы документации противоречат друг другу, выясни актуальную реализацию по исходникам, тестам и истории коммитов.

Не подстраивай архитектуру под устаревшие версии Horizon.

---

# 2. Основная стратегическая цель

Создать настолько мощную и удобную среду, чтобы пользователь мог разработать практически любую концептуально допустимую игровую механику Horizon:

- От простого нового меча до целой RPG.
- От нового животного до полноценной экосистемы существ.
- От обычного предмета до сложной инженерной системы.
- От нового биома до отдельного измерения.
- От небольшого эффекта до кинематографического события.
- От одного NPC до системы персонажей с памятью и интеллектом.
- От простой машины до космического аппарата.
- От визуально настраиваемого объекта до расширения самого движка.

Но не утверждай, что любой желаемый результат автоматически возможен.

**Долгосрочная цель — не бесконечный список встроенных функций, а расширяемая платформа, способная реализовать новые классы функций без переписывания всей IDE.**

Нужны три уровня создания модов:

### Beginner — No-Code

Пользователь ничего не знает о Rust и программировании.

Он выбирает шаблоны, меняет параметры, соединяет логические блоки, настраивает модели и получает работающий мод.

### Creator — Low-Code

Пользователь создаёт более сложные механики в визуальных редакторах, добавляет выражения, скрипты, правила поведения и собственные компоненты.

### Professional — Full-Code

Пользователь полностью управляет исходниками Rust, структурами Cargo, графикой, API движка, тестами и компиляцией.

Все три режима должны использовать максимально общую модель проекта и совместимые механизмы сборки.

---

# 3. Исследование лучших существующих программ

Проведи глубокое сравнение:

- MCreator.
- Blockbench.
- Blender.
- IntelliJ IDEA.
- Visual Studio Code.
- Visual Studio.
- Godot Editor.
- Unreal Engine Editor.
- Unity Editor.
- Roblox Studio.
- Minecraft Datapack Editors.
- GeckoLib ecosystem.
- Figura.
- Minecraft animation/modeling utilities.
- Shader editors.
- Particle/VFX graph editors.
- Node-based workflow tools.

Исследуй не только список возможностей, но и конкретные UX-механизмы:

- Как устроен проект.
- Как устроен интерфейс.
- Как создаётся новый объект.
- Как выполняется редактирование.
- Как работает Undo/Redo.
- Как обрабатываются ошибки.
- Как пользователь переключается между 3D и кодом.
- Как осуществляется импорт ресурсов.
- Как реализованы плагины.
- Как формируется готовая сборка.
- Как проект масштабируется до тысяч объектов.
- Что делает работу быстрой и приятной.
- Какие особенности пользователи критикуют.
- Что можно улучшить радикально.

Используй официальную документацию, GitHub-репозитории, исследования UX и реальные отзывы пользователей.

Подготовь сравнительную матрицу минимум по 30 критериям.

Не копируй чужой защищённый код, интерфейс или ассеты без проверки лицензий.

Определи собственное конкурентное позиционирование Horizon Studio.

---

# 4. Полная функциональная архитектура

Спроектируй следующие крупные подсистемы.

## A. Universal Project System

Один проект может содержать:

- Несколько модов.
- Исходники Rust.
- Контентные пакеты.
- Текстуры и модели.
- Звуки.
- Анимации.
- Шейдеры.
- Сущности.
- Предметы.
- Блоки.
- Измерения.
- Игровые правила.
- AI-поведение.
- Сценарии.
- Серверную логику.
- Пользовательские инструменты.
- Тестовые миры.

Предложи формат проекта с версионированием, графом зависимостей, инкрементальными сборками, миграциями и возможностью командной работы.

Изучи необходимость внутреннего промежуточного представления (IR), связывающего визуальные редакторы и генерацию кода.

## B. Professional IDE

Спроектируй:

- Встроенный Rust Code Editor.
- Monaco или альтернативу.
- rust-analyzer.
- LSP.
- Autocomplete.
- Semantic highlighting.
- Go to definition.
- Refactoring.
- Diagnostics.
- Integrated terminal.
- Cargo integration.
- Build profiles.
- Source maps.
- Error navigation.
- Debugger.
- Breakpoints.
- Profiling.
- Git integration.
- Code formatting.
- Code templates.
- Unit-test runner.
- Build cache.
- Project-wide search.
- Safe recovery after crashes.

Особенно исследуй:

**Как сделать, чтобы визуально созданный объект превращался в понятный Rust-код, который пользователь может менять, не разрушая весь визуальный проект?**

Рассмотри варианты:

1. Односторонняя генерация.
2. Двусторонняя синхронизация.
3. AST-based editing.
4. Stable generated regions.
5. Intermediate Representation.
6. Plugin-specific extensions.

Сравни ограничения и стоимость каждого варианта.

## C. Professional 3D Editor

Создай концепцию редактора уровня специализированного voxel/low-poly инструмента:

- Полноценный 3D viewport.
- Orbit, pan, zoom.
- Perspective/orthographic cameras.
- Transform gizmos.
- 3D selection.
- Object hierarchy.
- Layers.
- Bones.
- Rigging.
- Keyframe animation.
- Timeline.
- Animation curves.
- UV editing.
- Texture painting.
- Materials.
- Normal maps.
- Emissive maps.
- Particles.
- Lighting.
- Preview environments.
- Import/export.
- Live previews.
- Drag-and-drop.
- Undo/Redo.

Обязательно исследуй поддержку `.bbmodel`, Minecraft JSON, glTF и других полезных форматов.

Укажи, какие форматы реально поддерживает Horizon и какие потребуют адаптеров.

---

# 5. Создание любых игровых объектов

Разработай подсистемы для:

### Blocks & Items

Разнообразные формы, свойства, материалы, особые состояния, интерактивность, разрушение, инвентари, энергия, жидкости, освещение, анимации, нестандартные инструменты.

### Entities & Animals

Создание любых игровых существ:

- Реальные животные.
- Фантастические существа.
- Роботы.
- Боссы.
- Летающие и плавающие существа.
- Насекомые.
- Сложные многокомпонентные сущности.
- Пользовательские транспортные средства.

Пользователь должен визуально назначать модель, скелет, анимации, характеристики, физику, звуки и поведение.

### Entity Intelligence

Исследуй многослойную AI-систему:

- State Machines.
- Behavior Trees.
- GOAP.
- Utility AI.
- Navigation Meshes.
- Voxel pathfinding.
- Dynamic obstacle avoidance.
- Group behavior.
- Flocking.
- Herd behavior.
- Predator/prey simulation.
- Memory and perception.
- Reputation systems.
- Learning or adaptation.
- AI dialogue.
- Optional local LLM integration.
- NPC schedules and goals.

Сделай подробный план визуального AI Behavior Editor.

Отдельно исследуй, как ограничивать вычислительные затраты AI для больших миров и серверов.

---

# 6. Advanced Physics & Engineering

Это одно из наиболее важных направлений.

Мы хотим создавать в игре полноценные физические системы, а не только декоративные объекты.

Исследуй проектирование:

- Vehicles.
- Aircraft.
- Spacecraft.
- Rockets.
- Engines.
- Thrusters.
- Gravity systems.
- Aerodynamics.
- Buoyancy.
- Fluids.
- Constraints.
- Hinges and joints.
- Rigid bodies.
- Deformable bodies.
- Collisions.
- Structural integrity.
- Destruction physics.
- Electrical and mechanical networks.
- Energy transport.
- Mechanical automation.
- Large moving structures.

Пользователь должен иметь возможность, например, визуально собрать игровую ракету, задать её игровые физические параметры, разместить двигатели, запустить её и посмотреть симуляцию полёта.

Нужен режим **Physics Sandbox** с визуальной диагностикой сил, траекторий, столкновений и энергозатрат.

Реализм должен быть регулируемым: Arcade, Balanced, Simulation.

При проектировании ракет и взрывов ограничивайся игровыми симуляциями и безопасными абстрактными моделями. Не включай реальные инженерные инструкции по созданию оружия или ядерных устройств.

---

# 7. Ultimate Visual Effects Studio

Это отдельная приоритетная подсистема.

Нужен визуальный VFX Editor, способный создавать эффекты уровня современных игровых движков.

Изучи:

- Particle systems.
- GPU particles.
- Compute shaders.
- Volumetric fog.
- Volumetric lighting.
- Dynamic shadows.
- Bloom.
- Screen-space effects.
- Distortion.
- Refraction.
- Smoke.
- Sparks.
- Debris.
- Fire.
- Shockwaves.
- Heat haze.
- Lightning.
- Weather effects.
- Explosions.
- Fireworks.
- Magic.
- Portals.
- Energy beams.
- Lasers.
- Cinematic camera effects.
- Post-processing.
- Shader Graph.
- Material Graph.
- Procedural animation.
- Audio-reactive effects.
- LOD.
- VFX culling.
- Effect scalability settings.

Нужна нодовая система, в которой можно соединять:

Event → Emitter → Particle Simulation → Shader → Lighting → Audio → Camera Effect.

### Особый демонстрационный сценарий

Пользователь хочет создать очень масштабный фантастический игровой взрыв, визуально напоминающий кинематографический ядерный взрыв.

Предусмотри:

- Яркую вспышку.
- Визуальную ударную волну.
- Объёмное грибовидное облако.
- Дым и пыль.
- Динамическое освещение.
- Тряску камеры.
- Частицы разрушения.
- Звуковое сопровождение.
- Игровой урон по настраиваемым правилам.
- Настраиваемые изменения виртуального ландшафта.
- Несколько уровней графического качества.

Всё это — **исключительно визуальная игровая симуляция**, без моделирования реальной конструкции или оптимизации ядерного оружия.

Раздели VFX на визуальную и игровую составляющие, чтобы эффекты можно было отключать или упрощать без изменения логики сервера.

Укажи, какие возможности реализуемы внутри Horizon Studio, а какие потребуют интеграции с renderer/runtime Horizon.

---

# 8. Dimensions & World Generation

Нужен полноценный редактор миров и измерений.

Функции:

- Custom dimensions.
- World presets.
- Terrain generators.
- Noise graphs.
- Biome editors.
- Climate systems.
- Cave generation.
- Underground structures.
- Floating worlds.
- Sky islands.
- Alien planets.
- Custom gravity.
- Custom skies.
- Day/night cycles.
- Custom weather.
- Ocean generation.
- Structure placement.
- Spawn rules.
- Dimension portals.
- Streaming and chunk generation.
- Procedural materials.
- World preview.
- Seed visualization.

Проектируй систему с возможностью расширять её внешними генераторами и пользовательским кодом.

Нужен визуальный генератор биомов и ландшафтов с 3D-preview и настройкой графов шума.

Обязательно исследуй совместимость с реальной архитектурой хранения миров и генерации Horizon.

---

# 9. Visual Programming System

Это должна быть одна из ключевых особенностей Horizon Studio.

Спроектируй нодовую систему наподобие Unreal Blueprints, но адаптированную к Horizon.

Примеры:

- Player joins server.
- Entity spawns.
- Entity takes damage.
- Block destroyed.
- Item used.
- Timer expires.
- Collision occurs.
- Custom event triggered.
- AI perceives target.
- Dimension changes.
- Custom network message.

Логика должна быть:

- Типизированной.
- Расширяемой.
- Отлаживаемой.
- Версионируемой.
- Пригодной для компиляции.
- Совместимой с системой тестирования.

Нужны:

- Variables.
- Functions.
- Events.
- Loops.
- Branches.
- State.
- Timers.
- Async tasks where supported.
- Custom nodes.
- Error handling.
- Debug watches.
- Breakpoints.
- Performance inspector.

Определи, как нодовые графы преобразуются в Rust или другой поддерживаемый runtime, и какие гарантии корректности возможны.

Не обещай произвольное выполнение логики, если Horizon не предоставляет нужные хуки.

---

# 10. Ease of Use — исключительное удобство

Мы хотим, чтобы пользователю нравилось проводить в Horizon Studio много часов.

Разработай профессиональную UX-архитектуру.

Обязательно:

- Beautiful dark UI.
- Optional light theme.
- Minecraft-inspired design without unauthorized assets.
- Optional legally redistributable pixel fonts.
- Minecraft resource pack import.
- High-quality icons.
- Dockable panels.
- Resizable workspace.
- Multiple monitors.
- Split editor.
- Keyboard shortcuts.
- Command palette.
- Drag-and-drop.
- Templates.
- Project wizard.
- Global search.
- Context-sensitive inspector.
- Asset browser.
- Live preview.
- Undo/Redo.
- Autosave.
- Version history.
- Crash recovery.
- Accessible controls.
- Error explanations.
- Onboarding.
- Tooltips.
- Tutorials.
- Custom themes.
- Custom layouts.

Изучи, какие UI-framework и технологии наиболее подходят.

Особенно оцени текущую архитектуру Python + локальный HTTP-сервер + JavaScript.

Сравни возможную эволюцию в Tauri, Electron, Qt, Rust-native UI или гибридную систему.

Не рекомендуй переписывание только ради смены технологий.

Предложи измеримые UX-метрики:

- Время до первого работающего мода.
- Количество действий до типичной операции.
- Скорость загрузки проекта.
- Задержка 3D viewport.
- Время пересборки.
- Восстановление после ошибки.
- Простота поиска функций.
- Количество ошибок новичков.

---

# 11. Architecture & Extensibility

Предложи архитектуру, включающую при необходимости:

- Core application.
- Project model.
- Asset database.
- Plugin SDK.
- Code generation engine.
- Compiler bridge.
- Runtime capability discovery.
- 3D renderer.
- VFX engine.
- Physics authoring.
- Entity editor.
- AI graph editor.
- Build system.
- Mod validation engine.
- Preview runtime.
- Version compatibility layer.
- Packaging/publishing system.

Определи границы ответственности модулей, интерфейсы и механизм взаимодействия.

Особенно важно: пользовательские плагины должны иметь возможность добавлять **новые типы редакторов, сущностей, графов, компонентов и генераторов** без изменения ядра Studio.

Нужна стратегия API versioning и миграций проектов.

---

# 12. Horizon Engine Integration

Исследуй, как Horizon Studio может взаимодействовать с оригинальным Horizon и нашим форком:

https://github.com/pneqnp-iswr/unlicensed-horizon

Подготовь отдельную стратегию возможных изменений движка.

Не изменяй игровой движок автоматически.

Для каждого необходимого изменения укажи:

1. Какого API не хватает.
2. Где именно в исходниках находится соответствующая подсистема.
3. Можно ли реализовать функциональность обычным модом.
4. Нужно ли создавать PR в оригинальный Horizon.
5. Нужно ли поддерживать патч в собственном форке.
6. Какие появятся риски несовместимости.
7. Какие тесты необходимы.
8. Как обновляться при изменении upstream.

Предпочитай расширяемые публичные API перед многочисленными хрупкими патчами.

Не добавляй обходы лицензирования, аутентификации или распространение чужих игровых ассетов.

---

# 13. Performance & Reliability

Спроектируй производительность на уровне профессиональной IDE.

Нужны:

- Incremental compilation.
- Content-addressed caching.
- Background indexing.
- Async asset processing.
- Lazy loading.
- Virtualized explorer.
- Efficient rendering.
- Memory budgeting.
- GPU resource tracking.
- Profiling.
- Deterministic builds.
- Crash recovery.
- Large-project benchmarks.
- Automated compatibility testing.

Рассмотри сценарии проектов с тысячами объектов, большим количеством моделей, сложными эффектами и многочисленными AI-сущностями.

Не придумывай результаты бенчмарков. Предложи методику измерений, тестовые сцены и проверяемые целевые показатели.

---

# 14. Build, Test & Publish

Разработай универсальный процесс:

Create → Edit → Preview → Test → Compile → Debug → Package → Publish.

Он должен поддерживать разные виды модификаций в соответствии с реальными API Horizon.

Предусмотри:

- Local builds.
- Windows portable EXE releases.
- Linux/macOS distribution.
- GitHub Actions.
- Rust compilation.
- Official content mod validation.
- Automated game smoke tests.
- Static analysis.
- Regression tests.
- Version compatibility.
- Reproducible artifacts.
- SHA-256 checksums.
- Optional signing.
- Release channels.
- Plugin packaging.
- Mod dependencies.
- Mod publishing.
- Rollback.

Отдельно спроектируй возможность открыть проект, получить исходный код, изменить его вручную, собрать и запустить без использования визуального редактора.

---

# 15. Demo Projects — обязательные вертикальные сценарии

Разработай не менее восьми подробных end-to-end демонстрационных проектов, проверяющих всю архитектуру.

Обязательно включи:

**Demo A — Smart Animal**

Создание нового животного с моделью, текстурой, анимацией, поведением, звуками и интеллектом.

**Demo B — Intelligent Boss**

Босс с фазами, реакциями, поведением, визуальными эффектами и AI Behavior Graph.

**Demo C — Rocket Simulation**

Игровая ракета, собираемая визуально, с физикой, двигателями, эффектами, траекторией и управлением.

**Demo D — Cinematic Explosion**

Большой фантастический взрыв с объёмными эффектами, звуками и настраиваемым игровым воздействием.

**Demo E — Custom Dimension**

Новое измерение с собственным небом, биомами, ландшафтом, существами и порталами.

**Demo F — Automation System**

Конвейеры, механизмы, энергия, машины и взаимодействующие блоки.

**Demo G — RPG System**

Навыки, классы, задания, интерфейсы, враги, способности и сохранение прогресса.

**Demo H — Complete Rust Mod**

Проект с визуальными компонентами, пользовательским Rust-кодом, диагностикой, сборкой и запуском.

Для каждого демонстрационного проекта укажи:

- Что создаёт пользователь.
- Какими инструментами Studio пользуется.
- Какие API нужны.
- Какую часть можно сделать уже сейчас.
- Чего не хватает.
- Какие задачи roadmap это открывает.
- Как проверить результат автоматически.
- Что считать успешным завершением.

---

# 16. Главный результат — экспертный roadmap

Это самое важное.

Не ограничивайся обзором технологий или пожеланиями.

Построй реальную инженерную последовательность развития проекта.

Раздели roadmap на этапы:

### Foundation
Исправление существующих архитектурных проблем, тесты, проектная модель, стабильность, UX-фундамент.

### Professional Editor
Удобные редакторы, 3D, ассеты, текстуры, код, импорт/экспорт, отладка.

### Visual Modding
Ноды, генерация кода, компоненты, шаблоны, полноценные сборки.

### Gameplay Systems
Entity, AI, предметы, блоки, механики, GUI, миры.

### Simulation & VFX
Физика, транспорт, эффекты, shader graphs, продвинутый рендеринг.

### Native Engine Integration
Недостающие API Horizon, серверная логика, расширения движка.

### Platform & Ecosystem
SDK плагинов Studio, marketplace, совместная работа, документация, стабильные релизы.

### Advanced Creative Platform
Инструменты, позволяющие расширять Studio новыми категориями возможностей без переписывания ядра.

Для каждого этапа укажи:

- Цель.
- Конкретные подсистемы.
- Технические зависимости.
- Точные инженерные задачи.
- Архитектурные решения.
- Предварительную оценку сложности.
- Необходимые компетенции.
- Параллельно выполняемые работы.
- Риски.
- Тесты.
- Acceptance criteria.
- Definition of Done.
- Демонстрационный результат.
- Критерий перехода к следующему этапу.

Не назначай искусственные сроки без оценки ресурсов.

Сделай отдельные сценарии для одного разработчика с AI-инструментами, небольшой команды и полноценной команды.

Покажи критический путь и возможности параллельной разработки.

---

# 17. Техническая приоритизация

Для каждой крупной функции оцени:

- Пользовательскую ценность.
- Сложность.
- Архитектурный риск.
- Зависимость от Horizon.
- Тестируемость.
- Стоимость поддержки.
- Производительность.
- Повторное использование другими функциями.
- Значимость для сообщества.

Предложи формализованную систему приоритизации.

Особое внимание удели **platform-enabling features** — подсистемам, которые позволяют впоследствии реализовать десятки новых возможностей вместо одной.

Например, универсальная система компонентов для сущностей может быть ценнее, чем отдельный редактор одного типа животных.

---

# 18. Источники и достоверность

Работай как исследователь, а не как рекламный автор.

Для существенных технических решений указывай первичные источники:

- Официальные репозитории.
- Исходный код.
- API-контракты.
- Документацию.
- Лицензии.
- Issues.
- Pull requests.
- Release notes.
- Профильные исследования.

Разделяй:

**Verified fact / Engineering inference / Hypothesis / Future proposal.**

Если возможностей Horizon сейчас недостаточно, прямо указывай это.

Не называй технологии или функции «Rust-only», если они также реализуемы в Java. Вместо этого различай интеграцию с Rust-архитектурой Horizon и фундаментальные ограничения другого языка.

Не придумывай бенчмарки, реализованные функции или сроки.

Проверяй актуальные источники на дату подготовки исследования.

---

# 19. Обязательная структура итогового документа

Подготовь профессиональный документ под названием:

**HORIZON STUDIO — MASTER ENGINEERING ROADMAP & PLATFORM ARCHITECTURE**

Структура результата:

1. Executive Vision.
2. Verified Current State.
3. Critical Problems in Existing Code.
4. Competitive Benchmark.
5. Product Philosophy.
6. Ultimate Feature Taxonomy.
7. Technology Stack Recommendations.
8. Architecture Overview.
9. Component and Plugin Architecture.
10. Rendering, Physics and AI Architecture.
11. Visual Programming & Code Generation.
12. Horizon Integration Strategy.
13. UX/UI Design System.
14. Security & Asset Licensing.
15. Testing and Release Engineering.
16. Detailed Phased Roadmap.
17. Dependencies and Critical Path.
18. Prioritized Engineering Backlog.
19. Eight End-to-End Demo Projects.
20. Performance and Quality Targets.
21. Risks and Alternative Strategies.
22. First Three Concrete Development Iterations.
23. Long-Term Extensibility Strategy.
24. Final Technical Assessment.

Используй диаграммы Mermaid, таблицы зависимостей, схемы компонентов и конкретные технические примеры, когда это улучшает понимание.

Для каждого значимого архитектурного выбора подготовь краткий ADR: контекст, варианты, плюсы, минусы, решение и условия его пересмотра.

---

# 20. Первый практический план

После большого roadmap отдельно представь **первые три конкретные инженерные итерации**.

Для каждой итерации:

- Какие файлы текущего репозитория придётся изменить.
- Какие новые модули создать.
- Какие интерфейсы определить.
- Какие тесты написать.
- Какие технические долги устранить.
- Как проверить результат.
- Что показать пользователям.
- Что не следует делать преждевременно.

Раздели задачи по приоритету P0/P1/P2.

Это должен быть план, с которым другой инженер или AI-разработчик сможет открыть репозиторий и начать работу без дополнительного стратегического обсуждения.

---

# 21. Критическая экспертная проверка

Перед финализацией попробуй опровергнуть собственную архитектуру.

Ответь:

- Не превращаем ли мы Studio в чрезмерно сложный монолит?
- Не слишком ли рано создаём собственный 3D-движок?
- Какие решения лучше переиспользовать?
- Где выгоднее интегрировать Blockbench, а не повторять его?
- Нужна ли миграция с Python?
- Какие задачи требуют нативного Rust-кода?
- Как избежать зависимости от нестабильных API Horizon?
- Где визуальное программирование перестанет масштабироваться?
- Какие функции чрезмерно дороги?
- Как не испортить UX обилием возможностей?
- Что произойдёт после крупного изменения upstream?
- Какие решения через год создадут архитектурный тупик?
- Как обеспечить расширяемость без бесконечного технического долга?

Если первоначальная архитектура не выдерживает критики — пересмотри её.

---

# 22. Финальная оценка

В конце дай два набора оценок по шкале 0–10.

### Текущее состояние Horizon Studio

- Architecture.
- UI/UX.
- 3D Editing.
- Visual Programming.
- Native Rust Integration.
- Game Compatibility.
- Modding Capabilities.
- Extensibility.
- Build System.
- Testing.
- Reliability.
- Community Readiness.

### Качество предложенного roadmap

- Technical feasibility.
- Architectural coherence.
- Extensibility.
- User experience.
- Engineering precision.
- Risk management.
- Incremental deliverability.
- Competitive differentiation.
- Research confidence.
- Long-term sustainability.

Объясни слабые стороны и способы улучшения.

## Критически важное последнее требование

Не пытайся просто перечислить сотни функций.

Определи **минимальное количество мощных фундаментальных систем, комбинации которых позволят пользователям создавать практически неограниченное разнообразие игровых механик и контента**.

Наша цель — не программа с тысячей несвязанных кнопок.

Наша цель — **единая, мощная, расширяемая, приятная в работе и профессиональная среда творчества**, в которой человек может перейти от идеи к работающей игре, моду или расширению движка, независимо от того, умеет ли он программировать.

Работай глубоко, критически, с реальными источниками, техническими решениями и проверяемыми критериями.

**Начинай с аудита актуального GitHub-репозитория, затем подготовь полный Master Engineering Roadmap. Не приступай к изменениям исходного кода, пока roadmap не завершён.**
