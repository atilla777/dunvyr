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
- Реальные селекторы тестов — зарегистрированные маркеры pytest `unit` / `integration` (`--strict-markers`). Публичный командный интерфейс — корневой `Makefile` (`make lint`, `make test-unit`, `make test-integration`, `make test-affected` с этими же командами) — см. [tooling/commands](../tooling/commands.md); состав gate — в [testing](../../rules/testing.md).

## App-factory и health-эндпоинт

- Точка сборки — `dunvyr.main.create_app(*, engine=None, database_url=None)`: composition root, регистрирует роутеры (health + identity + campaigns + communication), кладёт engine/session factory и настройки (allowed origins, cookie Secure, rate limiters identity/campaigns, фабрики сервисов identity/campaigns, `guest_resolver_factory`, `campaign_membership_reader_factory`, `chat_service_factory`, `realtime_hub` и post-commit `campaign_event_publisher` для связи campaigns → communication) в `app.state`, подключает CORS-middleware (allow-headers: `Content-Type`, `Idempotency-Key`). При `DUNVYR_AUTO_MIGRATE=1` применяет Alembic-миграции к движку до старта — контракты контекстов и переменные окружения: [identity](identity.md), [campaigns](campaigns.md), [communication](communication.md). Модульного экземпляра приложения нет; ASGI-запуск: `uvicorn --factory dunvyr.main:create_app` (runtime-зависимость `websockets` — реальный WS-апгрейд в uvicorn; интеграционные тесты поднимают WS in-process без него).
- Контракт `GET /health` → `200` с телом `{"status": "ok", "database": "ok"}`; `database` проверяется реальным `SELECT 1` через сессию приложения, а не константой.
- Разрешение URL БД (в порядке приоритета): явный аргумент → `database_url` → переменная окружения `DUNVYR_DATABASE_URL` → default `sqlite:///./dunvyr.db` (файл рабочей БД и его WAL/SHM-sidecar-файлы игнорируются Git).

## База данных и миграции

- SQLAlchemy 2.x. На каждом SQLite-соединении включается `PRAGMA foreign_keys=ON`; для файловых БД включается WAL journaling (для `:memory:` — no-op).
- Схема рабочей БД создаётся только через Alembic (не `create_all`). Миграция `0001` создаёт единственную техническую таблицу `app_metadata` (`key` TEXT PRIMARY KEY, `value` TEXT NOT NULL); бизнес-миграции: `0002` (identity) — [identity](identity.md), `0003`–`0004` (campaigns: схема + уникальность псевдонима члена) — [campaigns](campaigns.md), `0005` (communication: единый поток событий чата) — [communication](communication.md). Авто-миграция при старте — opt-in `DUNVYR_AUTO_MIGRATE=1` (движок приложения, `DUNVYR_MIGRATIONS_DIR`, default `migrations` от cwd=backend).
- Alembic-окружение берёт URL из `sqlalchemy.url` ini-опции → `DUNVYR_DATABASE_URL` → default; поддерживает движок, инжектированный через `config.attributes["engine"]` (используется тестами).

## Тестовая архитектура и изоляция

- Тестовая SQLite — `sqlite+pysqlite:///:memory:` с `StaticPool`: один движок делят настоящий `alembic upgrade head` и приложение, поэтому миграции и запросы видят одну схему. Файлов рабочей БД тесты не создают и не меняют: интеграционный тест изоляции выполняет полный flow (миграции + TestClient `/health`) в `tmp_path` и утверждает отсутствие `*.db`/`*.db-wal` на диске.
- Integration-тесты поднимают приложение через FastAPI `TestClient` на мигрированной in-memory SQLite; unit-тесты не поднимают рабочую БД (два честных исключения — проверка pragma/подключения на in-memory-движке и проверка WAL на временной файловой БД в `tmp_path`).

## Архитектурные контракты (Import Linter)

Скелетные контракты (введены задачей dunvyr-68c.1; нарушение ловится проверкой — продемонстрировано red/green: временный межконтекстный импорт и обратный слоевой импорт давали red, после удаления — green):

1. запрет импорта чужих внутренних слоёв `domain`/`application`/`infrastructure`/`presentation` (контекст без слоёв не задаёт лишних). Изменено задачей dunvyr-u4k.2: исходная полная «независимость» заменена на этот контракт — межконтекстные импорты **только через `public/`** допустимы по правилу bounded-contexts (первый потребитель: campaigns → `identity.public`); wildcard-контракт «чужие domain/application/infrastructure» (п. 3) сохранён;
2. `shared` не импортирует доменные контексты;
3. запрет импорта чужих `domain`/`application`/`infrastructure`-слоёв (wildcard-контракт);
4. слоёвость app-level: `dunvyr.main` (composition root) > `dunvyr.presentation` > `dunvyr.infrastructure`.

Плюс по 4 контракта identity, campaigns и communication (слои `presentation > application > domain` и `infrastructure > application > domain`, запреты для `public`/`domain` каждого контекста) — см. [identity](identity.md), [campaigns](campaigns.md), [communication](communication.md). Итого **16** контрактов, все зелёные.

## Ограничения (ещё не существует)

Frontend-скелет — [frontend/skeleton.md](../frontend/skeleton.md); командный интерфейс, git hooks и E2E smoke — [tooling/commands.md](../tooling/commands.md). CI (dunvyr-68c.5). Гостевая идентичность — [identity](identity.md); кампании (срез организатора + гостевой срез join/отзыв) — [campaigns](campaigns.md); чат/WS и единый поток событий — [communication](communication.md). Остальная игровая доменная логика — будущие вехи; контексты кроме identity/campaigns/communication пока без слоёв-подкаталогов (честный минимум для пустых пакетов).
