# Кампании: домен, идемпотентное создание, отзывное приглашение, REST-контракт

> Подтверждённое поведение, введённое Beads-задачей dunvyr-u4k.2 (веха «Два гостя входят в одну кампанию», срез организатора). Нормативные источники: [multiplayer-and-access](../../product/multiplayer-and-access.md) §Кампания и встреча, §Организатор, §Приглашения, [security-and-privacy](../../rules/security-and-privacy.md) §Гостевой вход, §Контроль доступа, [bounded-contexts](../../rules/bounded-contexts.md) (владение campaigns, public-only потребление identity), [architecture](../../rules/architecture.md) (идемпотентность), [backend-and-data](../../rules/backend-and-data.md) §API contracts. Слой-прецедент и инфраструктура — [identity](identity.md), [backend/skeleton](skeleton.md).

## Домен campaigns (`dunvyr/campaigns/domain/`)

- `CampaignName` (замороженный VO): обрезка по краям, 1–60 Unicode-символов, без символов категории `C*` (управляющие/невидимые форматные). Нарушение — `InvalidCampaignName`. Правила приняты в задаче (локальная деталь по «Ограничение детализации»): продуктовое имя кампании обязательно, уникальность не требуется.
- `MaxSeats` (замороженный VO): целое 2–20 включительно, default `DEFAULT_MAX_SEATS = 6`; bool/float/строка отклоняются (`InvalidMaxSeats`). Организатор — обычный участник и занимает место; инвариант агрегата: `len(members) <= max_seats`.
- `Invitation` (замороженный VO): хранит **только** SHA-256 hex-хэш секрета (`hash_invitation_secret`); сырой секрет не живёт в доменном объекте. `Invitation.issue(secret)` хэширует свежий секрет и не сохраняет сырец; `revoke()` возвращает копию с `revoked=True` (immutable), `is_active = not revoked`. Невалидный хэш (не lowercase 64-hex) отклоняется инвариантом.
- `Membership`: `guest_id: UUID`, `nickname: str` (**снапшот** на момент вступления — список участников не читает таблицы identity), `role: organizer|player`, `joined_at` (timezone-aware).
- `Campaign` (Entity, замороженный dataclass): ровно **один** участник с ролью organizer, и он совпадает с `organizer_id` (инвариант `InvalidCampaign`); участники уникальны по `guest_id`; `idempotency_key: UUID`; `invitation: Invitation`; `created_at` timezone-aware. `Campaign.create(...)` создаёт кампанию с единственным участником-организатором; `revoke_invitation()` — копия с отозванным приглашением (endpoint/UI отзыва — задача u4k.3).
- Секрет приглашения: `secrets.token_urlsafe(32)` (256 бит, ~43 URL-safe символа) — тот же класс энтропии, что сессионный токен identity.

## Публичный контракт (`campaigns/public/`)

Пока ни один контекст не потребляет campaigns — модуль сознательно пуст (маркер пакета, без внутренних слоёв). Будущие snapshots/DTO для communication/gameplay появятся здесь.

## Application и потребление identity

- `CampaignService.create_campaign(command)`: предварительный поиск по `(organizer_id, idempotency_key)` — найденное возвращается как replay (`created=False`, **без** секрета); иначе доменная валидация, генерация секрета, `Campaign.create`, запись. Гонку закрывает БД-ограничение: `DuplicateIdempotencyKey` → перечитывание победившей записи (защита от повторов на уровне схемы, не только Python).
- `CampaignService.get_campaign(campaign_id, viewer_id)`: отсутствующая кампания → `CampaignNotFound`; не-член → `CampaignAccessDenied` (представление — ниже). Членство проверяет сервер в каждой операции.
- Порты: `UnitOfWork` (репозиторий кампаний), `Clock`, `IdFactory`, `InvitationSecretGenerator` (Protocol).
- Rate limit create: отдельный от identity in-process скользящий лимитер `CampaignSlidingWindowRateLimiter` — **свой бакет**, 10 запросов / 60 c per client IP, lock-защищённый, сбрасывается рестартом (принятое ограничение однопроцессного MVP, как у identity).
- Потребление identity — **только** `dunvyr.identity.public`: `GuestResolver` (резолв гостя по сырому токену cookie) и `SESSION_COOKIE_NAME`. Публичный контракт identity расширен аддитивно константой `SESSION_COOKIE_NAME = "dunvyr_session"` (единый источник истины: identity presentation импортирует её из public, см. [identity](identity.md)); campaigns не импортирует внутренние слои identity и не обращается к его таблицам — гости ссылаются opaque UUID-текстом без cross-context FK.

## REST-контракт (`campaigns/presentation/`, префикс `/api/campaigns`)

- `POST /api/campaigns` body `{"name": "...", "max_seats": 6}` (max_seats optional, default 6) + обязательный заголовок `Idempotency-Key: <uuid>` (клиент генерирует; отсутствие/не-UUID → `422`). Первый create → `201` с полным представлением кампании и **одноразовыми** `invitation.secret` + `invitation.path = "/join/<secret>"`; повтор тем же ключом того же организатора → `200`, та же кампания, `secret/path = null`, дублей не создаёт. Невалидные name/max_seats → `422` с текстом доменной ошибки. Аноним (нет/истекла сессия) → `403`. Защиты: Origin-проверка (allow-list, иначе `403`), rate limit (свой бакет, `429` + `Retry-After`). CORS allow-headers расширен `Idempotency-Key`.
- `GET /api/campaigns/{id}` — только членам: несуществующая → `404` `detail: "not_found"`; аноним или не-член → `403` `detail: "forbidden"` (без раскрытия существования). Ответ никогда не содержит секрет приглашения (только `invitation.active`).
- Схема ошибок следует [backend-and-data](../../rules/backend-and-data.md) §API contracts: `not_found`/`forbidden` в `detail`; имя кампании в UI-сообщениях фронтенда.

## Миграции и персистентность

- Бизнес-миграция `0003` (после identity `0002`): `campaigns_campaigns` (`id` TEXT PK, `name` TEXT, `max_seats` INTEGER, `organizer_id` TEXT + индекс, `idempotency_key` TEXT, `invitation_token_hash` TEXT **UNIQUE**, `invitation_revoked` BOOLEAN, `created_at` TEXT; `UNIQUE(organizer_id, idempotency_key)`) и `campaigns_members` (PK `(campaign_id, guest_id)`, FK → `campaigns_campaigns.id` ON DELETE CASCADE + индекс, `nickname` TEXT, `role` TEXT, `joined_at` TEXT). Префикс `campaigns_` — владение контекста (ownership-тест); UUID/datetime — TEXT (isoformat), как в identity.
- Авто-миграция `DUNVYR_AUTO_MIGRATE=1` (make dev, E2E) поднимает схему до `0003`; integration-тесты — собственный Alembic-pipeline. Схема только Alembic, не `create_all`.
- Персистентность проверена: файловая SQLite (tmp_path), два экземпляра приложения — после «рестарта» кампания и состав читаются, `alembic_version=0003`.

## Архитектурные контракты

- Скелетный контракт «независимость контекстов» заменён (задачей u4k.2) на **запрет импорта чужих внутренних слоёв** (domain/application/infrastructure/presentation всех семи контекстов): межконтекстные импорты **только** через `public/` — первая реальная пара campaigns→identity.public легитимна по правилу bounded-contexts. Wildcard-контракт «чужие domain/application/infrastructure» сохранён.
- Добавлены 4 контракта campaigns (по образцу identity): слои `presentation > application > domain` и `infrastructure > application > domain`; запрет `campaigns.public` импортировать внутренние слои; запрет `campaigns.domain` импортировать внешние слои. Итого 12 контрактов, все зелёные; unit-тест архитектуры дополнительно фиксирует, что единственный межконтекстный импорт campaigns — `dunvyr.identity.public`.
- Ownership: metadata campaigns содержит только `campaigns_*`; создание кампании не меняет счётчики строк identity-таблиц (интеграционные тесты).

## Фронтенд-срез

- После входа (`App`): форма «Название кампании» + кнопка «Создать кампанию» (`CreateCampaignForm`, блокировка при отправке, ошибки с `role="alert"`) → экран кампании (`CampaignScreen`): заголовок, «Мест занято N из M», ссылка-приглашение (абсолютный URL `window.location.origin + path`) с кнопкой «Скопировать ссылку» и статусами `role="status"`/`role="alert"`, панель «Участники» с «— организатор» и «(вы)». После обновления страницы кампания не восстанавливается (список «мои кампании» вне среза) — кнопка создания показывается снова.
- `api.ts`: `createCampaign(name, {maxSeats, idempotencyKey})` и типы; idempotency-key генерируется клиентом через `crypto.getRandomValues` (v4-UUID вручную — работает в insecure LAN HTTP, где `crypto.randomUUID` недоступен; крайний fallback `Math.random`). Секрет живёт только в состоянии экрана после create; повторный GET его не возвращает.

## Проверки на введённом снимке

`make lint` и затронутый набор зелёные (исполнитель и координатор независимо): **120** backend unit (campaigns: домен 34, service, tables, tokens, architecture + identity без изменений), **12** import-контрактов, **16** frontend Vitest (4 файла: App/CreateCampaignForm/CampaignScreen/LoginForm), **48** integration (campaigns REST 21: идемпотентность/чтение только членом/секрет не повторяется/негативные «секрет не в логах» (caplog)/rate limit/ownership/миграции; персистентность двумя экземплярами), **2** E2E smoke (desktop+mobile, сценарий не менялся).

## Ограничения (ещё не существует)

Присоединение по ссылке `/join/<secret>`, endpoint/UI отзыва приглашения и его эффект для гостей — задача u4k.3 (сейчас отзывность — только доменный инвариант). Секрет невосстановим: одноразовая выдача в ответе create, при потере ответа ссылку не показать снова. Списка «мои кампании» нет (F5 возвращает к созданию). Rate limit per-process, multi-worker не поддерживается. Страницы `/join` не существует; «секрет не в e2e-артефактах» подтверждено отсутствием campaigns-E2E-сценария и интеграционными проверками логов/ответов, браузерного flow с кампанией в E2E ещё нет (появится в u4k.5). `shared` не используется.
