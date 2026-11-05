# Командный интерфейс: Makefile, make dev, git hooks, изоляция прогонов

> Подтверждённое поведение, введённое Beads-задачей dunvyr-68c.3 (bootstrap-веха 1). Нормативные источники: [testing](../../rules/testing.md), [technology-and-infrastructure](../../rules/technology-and-infrastructure.md), [development-workflow](../../rules/development-workflow.md). Канонический fresh-clone flow — в корневом `README.md`.

## Публичный интерфейс команд

- Корневой `Makefile` — единственный публичный интерфейс локальных команд (нормативно: [testing](../../rules/testing.md)). Все цели выполняют команды через `mise exec -- ...`, поэтому `mise activate` не обязателен; требуются Linux, GNU make и mise в PATH. Версии рантимов — единственный источник истины `mise.toml` (см. [backend/skeleton](../backend/skeleton.md), [frontend/skeleton](../frontend/skeleton.md)).
- Цели и их состав (актуальная таблица — в [testing](../../rules/testing.md)): `make setup` (mise install + `uv sync` + `npm ci`), `make lint`, `make test-unit`, `make test-integration`, `make test-affected`, `make dev`, `make hooks`, `make help`.
- `make test-affected SCOPE=<backend|frontend|all> ARGS='<селекторы>'` — честная передача нативных селекторов (pytest пути/`-k`/`-m`; паттерны файлов Vitest), собственного `--changed`/dynamic-селектора нет. `SCOPE` по умолчанию `all` (одни и те же `ARGS` в оба стека); пустой `ARGS` или неизвестный `SCOPE` — usage-ошибка с exit 2. Подтверждено: `SCOPE=backend ARGS='tests/unit/test_app.py'` → 3 passed против 6 в полном `-m unit`.
- Изоляция прогонов: backend-тесты выполняются на in-memory SQLite в своём процессе (файлов рабочей БД не создают), `TestClient` без сетевых портов, frontend — jsdom без браузера (см. [backend/skeleton](../backend/skeleton.md)). `RUN=<id>` на тест-целях задаёт отдельный pytest cache (`-o cache_dir=.pytest_cache/run-<id>` внутри игнорируемого `.pytest_cache/`). Подтверждено: параллельные `make test-unit RUN=p1` и `make test-integration RUN=p2` — оба зелёные.

## `make dev`: LAN-запуск одной командой

- `scripts/dev.sh` поднимает backend (`uvicorn --factory dunvyr.main:create_app`) и frontend (Vite через `DUNVYR_DEV_HOST` + `--port`), печатает локальные и LAN-адреса и предупреждения: listener `0.0.0.0` требует firewall только для доверенной LAN; обычный HTTP — только доверенная LAN (для интернета обязателен HTTPS); CORS/allowed origins на backend не настроены — потребуется, когда frontend начнёт вызывать API (сейчас страница API не вызывает).
- Слушатель по умолчанию — сознательный `0.0.0.0` (решение задачи 68c.3: `make dev` — LAN-режим; raw `npm run dev` остаётся на localhost — см. [frontend/skeleton](../frontend/skeleton.md)). Переопределения: `DUNVYR_DEV_HOST` (например `127.0.0.1`), `DUNVYR_BACKEND_PORT` (8000), `DUNVYR_FRONTEND_PORT` (5173). При `DUNVYR_DEV_HOST=127.0.0.1` LAN-доступ закрыт.
- Надзор процессов: каждый сервер в своём process group (`setsid`); Ctrl+C/SIGTERM останавливает оба без сирот; смерть одного процесса гасит второй с ненулевым exit. Подтверждено на снимке задачи: после остановки порты свободны и процессов нет; при смерти backend (невалидный порт) frontend погашен, exit ненулевой.
- LAN-доступ проверен curl-ом по реальному LAN-IPv4 (не localhost): `GET /health` → `{"status":"ok","database":"ok"}`, `GET /` → HTML страницы — и в worktree, и в свежем клоне снимка. Открытие страницы с телефона — акт приёмки вехи (владелец), не автоматическая проверка.

## Git hooks

- Установка — `make hooks`: копирование `scripts/hooks/pre-commit` и `scripts/hooks/pre-push` в `$(git rev-parse --git-path hooks)` (копия, не symlink — hooks в общем git-dir не должны зависеть от расположения worktree). Hooks локальны для клона и не версионируются Git.
- `pre-commit` — только staged-файлы (ACMR): `.py` в `backend/` → `ruff check` + `ruff format --check`; `.ts/.tsx/.js/.jsx` в `frontend/` → `eslint` + `prettier --check`. Без релевантных файлов — быстрый exit 0; без E2E. Подтверждено: заведомо плохой `.py` (F401) → commit отклонён, exit 1.
- `pre-push` — backend `pytest -m unit` + `lint-imports`, frontend `npm run test`; без браузеров. Подтверждено: временный падающий unit-тест → push отклонён, exit 1. Hooks не заменяют полный gate публикации (нормативно: [testing](../../rules/testing.md)).

## Ограничения (ещё не существует)

`make test-e2e-smoke`, `make test-e2e-full`, `make test-ci` и Playwright — задача dunvyr-68c.4; CI-файл GitHub Actions — dunvyr-68c.5. CORS/allowed origins на backend — будущая настройка при появлении реальных API-вызовов с LAN-источников. mise-таски-делегаты сознательно не заведены (Makefile — единственный публичный интерфейс). Проверка страницы в реальном браузере — ручной шаг; автоматизированный browser smoke появится с E2E-задачей.
