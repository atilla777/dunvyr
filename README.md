# Dunvyr

Dunvyr — локальная многопользовательская веб-платформа для совместных настольных RPG с AI Dungeon Master. Первый вертикальный продукт: короткое законченное киберпанк-приключение на 1–2 встречи; правила универсальны для разных сеттингов.

**Backend- и Frontend-скелеты приложения уже созданы**: `backend/` — FastAPI app-factory с health-эндпоинтом, SQLAlchemy 2.x + Alembic, pytest, Ruff, mypy и Import Linter; `frontend/` — Vite + React + TypeScript strict, ESLint/Prettier, Vitest + Testing Library и минимальная страница. Корневой `Makefile` и git hooks уже созданы; Playwright/E2E и CI ещё не созданы — это следующие bootstrap-задачи.

## Где читать

- [Точка входа AI-агента](AGENTS.md)
- [OKF Bundle](docs/index.md)
- [Требования](docs/product/index.md)
- [Правила](docs/rules/index.md)
- [Что уже решено и что открыто](docs/product/decisions-and-open-questions.md)

## Быстрый старт

Нужны Linux, GNU make и `mise` в PATH. Версии Python, `uv` и Node фиксирует корневой `mise.toml`; `mise activate` не обязателен, потому что все цели Makefile запускают команды через `mise exec -- ...`.

```bash
make setup          # mise install + uv sync (backend) + npm ci (frontend)
make dev            # backend на :8000 и frontend на :5173, LAN-listener по умолчанию
make lint
make test-unit
make test-integration
make test-affected SCOPE=backend ARGS='tests/unit/test_app.py'
make test-affected SCOPE=frontend ARGS='src/App.test.tsx'
make hooks          # установить pre-commit и pre-push в git hooks
```

`make help` — список целей. `make test-affected` передаёт нативные селекторы без собственного `--changed`: для `SCOPE=backend` это пути/`-k`/`-m` pytest, для `SCOPE=frontend` — паттерны файлов Vitest; `SCOPE=all` (по умолчанию) передаёт те же `ARGS` обоим стекам. Пустой `ARGS` — usage-ошибка с ненулевым кодом. На тест-целях `RUN=<id>` включает отдельный pytest cache `.pytest_cache/run-<id>`, чтобы параллельные прогоны не делили артефакты.

## Backend

Версия Python и `uv` зафиксированы в корневом `mise.toml`; Ruff, mypy, pytest и Import Linter — dev-зависимости проекта из `backend/pyproject.toml`, точные версии — в `backend/uv.lock`.

Под капотом `make setup`, `make lint` и тестовых целей (те же команды вручную из `backend/`):

```bash
mise exec -- uv sync              # создаёт backend/.venv из uv.lock (make setup)
mise exec -- uv run ruff check .
mise exec -- uv run ruff format --check .
mise exec -- uv run mypy
mise exec -- uv run pytest -m unit
mise exec -- uv run pytest -m integration
mise exec -- uv run pytest
mise exec -- uv run lint-imports
```

Если mise активирован в shell (`mise activate`), префикс `mise exec --` не нужен: достаточно `uv sync` и `uv run ...` из `backend/`. Проверить версию Python: `mise exec -- python --version` → `Python 3.14.10`.

Integration-тесты применяют настоящий Alembic pipeline к SQLite в памяти (`sqlite+pysqlite:///:memory:`); файл рабочей БД при тестах не создаётся. Миграции вручную: `mise exec -- uv run alembic upgrade head` (URL — из `DUNVYR_DATABASE_URL`, по умолчанию `sqlite:///./dunvyr.db`).

## Frontend

Версия Node и npm зафиксированы в корневом `mise.toml`; React, Vite, TypeScript, ESLint, Prettier, Vitest и Testing Library — dev-зависимости из `frontend/package.json`, точные версии — в `frontend/package-lock.json`.

Под капотом `make setup`, `make lint` и `make test-unit` (те же команды вручную из `frontend/`):

```bash
mise exec -- npm ci               # воспроизводимая установка из package-lock.json (make setup)
mise exec -- npm run lint
mise exec -- npm run format:check
mise exec -- npm run typecheck
mise exec -- npm run test
```

Запуск dev-сервера: `mise exec -- npm run dev` → http://localhost:5173 по умолчанию. Для доступа из LAN задайте `DUNVYR_DEV_HOST` (LAN-IP или `0.0.0.0`) только после настройки firewall и allowed origins; `make dev` делает это для обоих серверов сразу (см. ниже).

Если mise активирован в shell, префикс `mise exec --` не нужен. Проверить версию Node: `mise exec -- node --version` → `v24.22.2`.

## LAN и `make dev`

`make dev` запускает backend и frontend одной командой и печатает локальные и LAN-адреса. Ctrl+C/SIGTERM останавливает оба процесса, не оставляя сирот.

```bash
make dev                                  # оба сервера на 0.0.0.0 (осознанный LAN-listener)
DUNVYR_DEV_HOST=127.0.0.1 make dev        # только этот компьютер
DUNVYR_BACKEND_PORT=9000 DUNVYR_FRONTEND_PORT=5174 make dev
```

| Переменная | По умолчанию | Назначение |
| --- | --- | --- |
| `DUNVYR_DEV_HOST` | `0.0.0.0` | Адрес прослушивания обоих серверов; для локального режима — `127.0.0.1`. |
| `DUNVYR_BACKEND_PORT` | `8000` | Порт backend (`GET /health`). |
| `DUNVYR_FRONTEND_PORT` | `5173` | Порт Vite dev-сервера. |

С другого устройства в той же доверенной LAN открывайте `http://<LAN-IPv4>:5173/` (health backend — `http://<LAN-IPv4>:8000/health`). Использовать `localhost` с телефона нельзя: он указывает на само устройство. Если `DUNVYR_DEV_HOST=127.0.0.1`, доступ из LAN закрыт.

Ограничения и предупреждения:

- Listener `0.0.0.0` открывает порты на всех интерфейсах. Firewall должен разрешать `8000`/`5173` только из доверенной LAN.
- Обычный HTTP допустим только в доверенной LAN; для доступа из интернета обязателен HTTPS.
- Backend пока не настраивает CORS/allowed origins. Когда frontend начнёт вызывать API с LAN-адресов, потребуется отдельная настройка; сейчас страница API не вызывает. Это известное будущее ограничение, а не реализованная защита.

## Git hooks

`make hooks` копирует `scripts/hooks/pre-commit` и `scripts/hooks/pre-push` в `$(git rev-parse --git-path hooks)` (именно копирование, чтобы hooks не зависели от расположения worktree):

- `pre-commit` — только staged-файлы: для `.py` из `backend/` запускает `ruff check` и `ruff format --check`; для `.ts/.tsx/.js/.jsx` из `frontend/` — `eslint` и `prettier --check`. Без E2E; если релевантных файлов нет — быстрый выход.
- `pre-push` — backend `pytest -m unit` + `lint-imports`, frontend `npm run test`; без браузеров.

Hooks переустанавливаются повторным `make hooks`; они не запускают E2E и не заменяют полный gate публикации.

## Среда агентной разработки (установлена)

- **MIS** установлен из проверенного upstream https://github.com/atilla777/mis; точная ревизия зафиксирована в `.opencode/mis-installation` — проверяй этот файл, а не этот README.
- **OpenCode 2.x** с native worktree (`.sdlc/worktrees`) и профилями агентов `standard`/`advanced`.
- **Beads `bd`** с embedded Dolt; история трекера публикуется в `refs/dolt/data` этого же Git remote.
- Доступные операции: `/mis-install`, `/mis-plan`, `/mis-run`, `/mis-bug`, `/mis-status`, `/mis-update`.

Обновление MIS — только явно через `/mis-update` по актуальной процедуре upstream README; самовольные изменения установленного пакета запрещены.

## Публикация изменений

Интеграция в `main` — **прямая публикация по протоколу MIS** (`mis-proj-op-publish-change`): полный обязательный gate локально на интегрированном снимке до push, независимый read-only AI-review, non-force push с read-back, CI GitHub Actions на push пост-фактум (решение владельца 2026-11-05). Закрытая Task означает подтверждённую публикацию, а не продуктовую приёмку. Детали — в [development-workflow](docs/rules/development-workflow.md).

## Что дальше

1. `/mis-plan` — план первой вехи: технический bootstrap (скелет FastAPI + React, реальные `make`-команды из [testing.md](docs/rules/testing.md), CI на push в `main`, git hooks, доступный по LAN запуск).
2. `/mis-run` — реализация задач вехи с проверками, независимым review и публикацией по протоколу.

Документация различает подтверждённые продуктовые решения, предложения для реализации и открытые параметры; открытые параметры не принимать молча.
