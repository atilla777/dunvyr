# Гостевая идентичность: домен, сессии, REST-контракт, cookie, миграции

> Подтверждённое поведение, введённое Beads-задачей dunvyr-u4k.1 (веха «Два гостя входят в одну кампанию»). Нормативные источники: [multiplayer-and-access](../../product/multiplayer-and-access.md) §Гостевая идентичность, [security-and-privacy](../../rules/security-and-privacy.md) §Гостевой вход, [bounded-contexts](../../rules/bounded-contexts.md), [architecture](../../rules/architecture.md), [backend-and-data](../../rules/backend-and-data.md), [domain-design](../../rules/domain-design.md). Первый доменный контекст со слоями; инфраструктура скелета — [backend/skeleton](skeleton.md).

## Домен identity (`dunvyr/identity/domain/`)

- `Nickname` (замороженный VO): входная строка обрезается по краям; после обрезки 1–32 Unicode-символа, без символов Unicode-категории `C*` (управляющие и невидимые форматные — нельзя сымитировать пустое имя), минимум один непробельный. Нарушение — `InvalidNickname` (подкласс `ValueError`). **Уникальность псевдонимов не поддерживается** (принято в задаче): гостевая идентичность — это сессия, а не имя; коллизии отображаемых имён — предмет членства кампании в поздних задачах.
- `Guest` (Entity): `id: UUID`, `nickname: Nickname`, `created_at` (timezone-aware; наивные datetime запрещены инвариантом).
- `GuestSession` (Entity): `token_hash`, `guest_id`, `created_at`, `expires_at`; срок жизни фиксированный при создании — 30 дней (`SESSION_LIFETIME`); инвариант `expires_at > created_at`; `is_valid_at(now)` — `now < expires_at`, истёкшая сессия обрабатывается как отсутствующая.
- Opaque-токен: `secrets.token_urlsafe(32)` (256 бит, ~43 URL-safe символа). В SQLite хранится **только SHA-256-хэш** токена (`hash_session_token`); сырой токен существует только в cookie и в момент Set-Cookie — утечка файла БД не даёт воспроизводимой credential-подписи.

## Публичный контракт (`dunvyr/identity/public/`)

Для будущих потребителей (campaigns и поздние контексты): `GuestSnapshot` (замороженный dataclass `id: UUID`, `nickname: str`) и `GuestResolver` (`Protocol`, `resolve_guest(session_token: str | None) -> GuestSnapshot | None`) — его удовлетворяет `IdentityService`. Public не импортирует внутренние слои (import-linter), не экспортирует ORM/SQLAlchemy/Pydantic.

## Application и infrastructure

- `IdentityService.create_session(raw_nickname)` атомарно создаёт `Guest` + `GuestSession` (одна короткая транзакция UnitOfWork) и возвращает `IssuedSession(token, GuestSnapshot)`; `resolve_guest(token)` резолвит гостя по хэшу токена. Порты — `Clock`, `IdFactory`, `TokenGenerator`, `UnitOfWork`/репозитории (Protocol).
- Репозитории — SQLAlchemy Core (`identity/infrastructure/tables.py`): таблицы только для типизированных запросов, схема создаётся исключительно Alembic. UUID и datetime хранятся как `TEXT` (isoformat).
- Rate limit (примитивный, принят в задаче): скользящее окно 10 запросов / 60 секунд per client IP, in-process (lock-защищённый счётчик); рестарт процесса сбрасывает счётчики — принятое ограничение однопроцессного MVP.

## REST-контракт (`identity/presentation/`, префикс `/api/identity`)

- `POST /api/identity/sessions` body `{"nickname": "..."}` → `201` `{"id": "<uuid>", "nickname": "..."}` + `Set-Cookie: dunvyr_session=…; HttpOnly; SameSite=Lax; Path=/; Max-Age=2592000`. Флаг `Secure` по умолчанию **выключен** — осознанная dev-конфигурация для локального HTTP; включается `DUNVYR_COOKIE_SECURE=1` (HTTPS). Невалидный псевдоним → `422` с текстом доменной ошибки.
- `GET /api/identity/me` → `200` `{"id", "nickname"}` при действующей сессии; `401` при отсутствии/истечении. Сессионный токен никогда не возвращается в теле ответа, URL и логах (проверено тестами, включая отсутствие в `localStorage`/`document.cookie` на фронтенде).
- State-changing защита: `POST` требует заголовок `Origin`, входящий в allow-list, иначе `403` (CSRF/origin-проверка поверх `SameSite=Lax`); GET без Origin-проверки. Превышение rate limit → `429` + `Retry-After` (1–60 c). Non-browser клиенты (curl, скрипты) передают допустимый `Origin` явно — пример в корневом `README.md`.
- CORS: `CORSMiddleware` из того же allow-list (`allow_credentials=True`, методы GET/POST/OPTIONS, заголовок Content-Type). Переменная `DUNVYR_ALLOWED_ORIGINS` (comma-separated; default `http://localhost:5173,http://127.0.0.1:5173`; пустое значение → default).
- В dev браузер работает с API **same-origin через Vite-прокси `/api`** (target `DUNVYR_BACKEND_ORIGIN`, default `http://127.0.0.1:8000`) — см. [frontend/skeleton](../frontend/skeleton.md); `make dev` подставляет backend `DUNVYR_ALLOWED_ORIGINS` c LAN-IP, loopback и localhost на порту frontend — см. [tooling/commands](../tooling/commands.md).

## Миграции и персистентность

- Бизнес-миграция `0002` (после технической `0001`): `identity_guests` (`id` TEXT PK, `nickname` TEXT NOT NULL, `created_at` TEXT NOT NULL) и `identity_sessions` (`id` TEXT PK, `token_hash` TEXT NOT NULL UNIQUE, `guest_id` TEXT FK → `identity_guests.id` ON DELETE CASCADE, индекс `ix_identity_sessions_guest_id`, `created_at`, `expires_at`). Префикс `identity_` обозначает владение контекста; чужие таблицы identity не читает и не пишет (тест ownership-префикса).
- Авто-миграция при старте — opt-in: `DUNVYR_AUTO_MIGRATE=1` заставляет `create_app` выполнить `alembic upgrade head` на движке приложения (`DUNVYR_MIGRATIONS_DIR`, default `migrations` от cwd=backend; отсутствующий каталог — явная `RuntimeError`). `make dev` и E2E webServer её включают; integration-тесты сохраняют собственный явный pipeline `apply_migrations` (tests/integration/support.py). Схема рабочей БД — только Alembic, не `create_all`.
- Персистентность проверена: файловая SQLite (tmp_path) с двумя экземплярами приложения — после «рестарта» `GET /api/identity/me` возвращает того же гостя; ручной прогон `make dev` создал `backend/dunvyr.db` миграцией (`alembic_version=0002`).

## Архитектурные контракты

Import Linter — 8 контрактов: 4 скелетных (см. [backend/skeleton](skeleton.md)) + 4 identity: слои `presentation > application > domain` и `infrastructure > application > domain`; запрет `identity.public` импортировать внутренние слои; запрет `identity.domain` импортировать внешние слои (включая public). Независимость контекстов (запрет импорта campaigns и других) покрывается скелетным контрактом независимости.

## Проверки на введённом снимке

`make lint` и полный gate `make test-ci` зелёные (дважды: исполнитель и координатор): 64 backend unit (TDD-домен: nickname/session/service/tokens/rate limit/config), 8 import-контрактов, 6 frontend Vitest, 25 integration (REST-сценарии, cookie-флаги, origin/CSRF, rate limit, негативные «токен нигде», персистентность), 2 E2E smoke (desktop+mobile, сценарий не менялся).

## Ограничения (ещё не существует)

Выход (logout), смена псевдонима, кампании/приглашения, чат/WebSocket, presence — следующие задачи вехи. Rate limit и счётчики — per-process: несколько uvicorn-workers не поддерживаются (однопроцессный MVP). Уникальность псевдонимов сознательно не enforced. `fetchCurrentGuest` на фронтенде трактует любой не-OK ответ как «аноним» и показывает форму входа (тонкий срез).
