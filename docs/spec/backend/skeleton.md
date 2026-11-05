# Backend-скелет: toolchain, app-factory, миграции, тестовая архитектура

> Подтверждённое поведение, введённое Beads-задачей dunvyr-68c.1 (bootstrap-веха 1). Нормативные источники: [technology-and-infrastructure](../../rules/technology-and-infrastructure.md), [bounded-contexts](../../rules/bounded-contexts.md), [architecture](../../rules/architecture.md), [backend-and-data](../../rules/backend-and-data.md), [testing](../../rules/testing.md). Канонический fresh-clone flow — в корневом `README.md`.

## Toolchain и команды

- Версии рантимов — единственный источник истины: корневой `mise.toml` (`python = "3.14.10"`, `uv = "0.13.7"`); файла `.python-version` нет. uv настроен с `python-preference = "only-system"` (`backend/pyproject.toml`), поэтому mise-пин Python авторитетен и uv не предпочтёт собственную managed-версию. Инструменты проверок — dev-зависимости проекта: `backend/pyproject.toml` + `backend/uv.lock` (точные версии в lock).
- Свежий клон: `mise install` → из `backend/`: `uv sync` → проверки.
- Реальные команды проверок (из `backend/`, все зелёные на снимке задачи):
  - `uv run ruff check .` и `uv run ruff format --check .` (lint/format, target py314);
  - `uv run mypy` (strict на `src/dunvyr`);
  - `uv run pytest -m unit`, `uv run pytest -m integration`, `uv run pytest`;
  - `uv run lint-imports` (архитектурные контракты).
- Реальные селекторы тестов — зарегистрированные маркеры pytest `unit` / `integration` (`--strict-markers`). `make`-обёрток пока нет — это задача dunvyr-68c.3; состав будущего gate — в [testing](../../rules/testing.md).

## App-factory и health-эндпоинт

- Точка сборки — `dunvyr.main.create_app(*, engine=None, database_url=None)`: composition root, регистрирует роутеры, кладёт engine/session factory в `app.state`. Модульного экземпляра приложения нет; ASGI-запуск: `uvicorn --factory dunvyr.main:create_app`.
- Контракт `GET /health` → `200` с телом `{"status": "ok", "database": "ok"}`; `database` проверяется реальным `SELECT 1` через сессию приложения, а не константой.
- Разрешение URL БД (в порядке приоритета): явный аргумент → `database_url` → переменная окружения `DUNVYR_DATABASE_URL` → default `sqlite:///./dunvyr.db` (файл рабочей БД и его WAL/SHM-sidecar-файлы игнорируются Git).

## База данных и миграции

- SQLAlchemy 2.x. На каждом SQLite-соединении включается `PRAGMA foreign_keys=ON`; для файловых БД включается WAL journaling (для `:memory:` — no-op).
- Схема рабочей БД создаётся только через Alembic (не `create_all`). Миграция `0001` создаёт единственную техническую таблицу `app_metadata` (`key` TEXT PRIMARY KEY, `value` TEXT NOT NULL) — бизнес-таблиц нет.
- Alembic-окружение берёт URL из `sqlalchemy.url` ini-опции → `DUNVYR_DATABASE_URL` → default; поддерживает движок, инжектированный через `config.attributes["engine"]` (используется тестами).

## Тестовая архитектура и изоляция

- Тестовая SQLite — `sqlite+pysqlite:///:memory:` с `StaticPool`: один движок делят настоящий `alembic upgrade head` и приложение, поэтому миграции и запросы видят одну схему. Файлов рабочей БД тесты не создают и не меняют: интеграционный тест изоляции выполняет полный flow (миграции + TestClient `/health`) в `tmp_path` и утверждает отсутствие `*.db`/`*.db-wal` на диске.
- Integration-тесты поднимают приложение через FastAPI `TestClient` на мигрированной in-memory SQLite; unit-тесты не поднимают рабочую БД (два честных исключения — проверка pragma/подключения на in-memory-движке и проверка WAL на временной файловой БД в `tmp_path`).

## Архитектурные контракты (Import Linter)

Четыре контракта, все зелёные; нарушение ловится проверкой (продемонстрировано red/green в задаче: временный межконтекстный импорт и обратный слоевой импорт давали red, после удаления — green):

1. независимость семи доменных контекстов (`identity`, `campaigns`, `characters`, `adventures`, `gameplay`, `communication`, `narration`); `shared` вне набора — контексты могут импортировать `shared`;
2. `shared` не импортирует доменные контексты;
3. запрет импорта чужих `domain`/`application`/`infrastructure`-слоёв (wildcard-контракт; сегодня строже — межконтекстных импортов нет вовсе, пока не появятся `public/`-контракты);
4. слоёвость app-level: `dunvyr.main` (composition root) > `dunvyr.presentation` > `dunvyr.infrastructure`.

## Ограничения (ещё не существует)

Frontend-скелет — [frontend/skeleton.md](../frontend/skeleton.md). `Makefile`/`make`-цели и git hooks (dunvyr-68c.3), Playwright/E2E (dunvyr-68c.4), CI (dunvyr-68c.5). WebSocket, игровая доменная логика и бизнес-таблицы — будущие вехи; layout контекстов пока без слоёв-подкаталогов (честный минимум для пустых пакетов).
