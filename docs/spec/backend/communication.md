# Communication: чат кампании в реальном времени, единый поток событий, WebSocket, доставка после commit

> Подтверждённое поведение, введённое Beads-задачами dunvyr-u4k.4 (веха «Два гостя входят в одну кампанию», срез чата) и dunvyr-u4k.5 (reconnect-протокол клиента, сквозной E2E двух гостей). Нормативные источники: [communication-and-journal](../../product/communication-and-journal.md) §Единый поток, [architecture](../../rules/architecture.md) §Транзакционность и доставка, §Прямая операция и событие, [backend-and-data](../../rules/backend-and-data.md) §REST и WebSocket, §API contracts, [security-and-privacy](../../rules/security-and-privacy.md) §Гостевой вход, §Контроль доступа, [frontend](../../rules/frontend.md) §Real-time UX, §Mobile, [bounded-contexts](../../rules/bounded-contexts.md) (владение communication). Слой-прецеденты и потребляемые контракты — [identity](identity.md), [campaigns](campaigns.md), [backend/skeleton](skeleton.md).

## Домен communication (`dunvyr/communication/domain/`)

- `MessageAuthor` (замороженный VO): «проверенный член кампании» — `campaign_id: UUID`, `guest_id: UUID`, `nickname` (снапшот на момент отправки; правила псевдонима те же, что в campaigns: 1–32 символа, без краевого whitespace и управляющих `C*`, кроме `\n`/`\t`).
- `Message` (замороженная Entity): `id: UUID`, `campaign_id`, `author_id`, `author_nickname`, `client_message_id: UUID`, `content`, `created_at` (timezone-aware; naive отклоняется). Инварианты (`InvalidMessage`): контент — строка, после обрезки краёв непустая и ≤ `MESSAGE_MAX_LENGTH = 2000` символов, без управляющих `C*` (кроме `\n`/`\t`); обрезка выполняется доменом (в хранилище и на проводе — уже обрезанный текст). `Message.create` требует `MessageAuthor` с `author.campaign_id == campaign_id` — автор конструируется только для члена своей кампании; фактическая проверка членства выполняется сервисом через публичный контракт campaigns (домен БД не читает).
- События потока — immutable (замороженные dataclass) с обязательными полями конверта: `event_id: UUID` (серверный), `campaign_id`, `sequence: int ≥ 1` (нарушения — `InvalidEvent`). `MessageEvent` несёт `Message` (кампания события = кампания сообщения); `MemberJoinedEvent` несёт `ChatMember` (`guest_id`, `nickname`, `role: organizer|player`, `joined_at` timezone-aware). `ChatEvent = MessageEvent | MemberJoinedEvent` — **единый хронологический поток** обоих типов.
- Хронологический порядок: `sequence` монотонный в рамках кампании, присваивается сервером в той же короткой транзакции, что и запись события (см. БД); клиент сортирует и дедуплицирует по `event_id`/`sequence`.

## Потребляемые публичные контракты (только `public/`)

- `dunvyr.identity.public`: `GuestResolver` + `SESSION_COOKIE_NAME` — резолв cookie-сессии, как у campaigns.
- `dunvyr.campaigns.public` (расширен этой задачей, см. [campaigns](campaigns.md) §Публичный контракт): `CampaignMembershipReader.find_member(campaign_id, guest_id) → CampaignMemberSnapshot | None` — единственный способ проверки членства; `CampaignEventPublisher.member_joined(campaign_id, member)` — post-commit порт, через который campaigns сообщает о вступлении гостя (реализация-адаптер — communication, вяжется в composition root; campaigns не импортирует communication, цикла public API нет).
- Communication не импортирует внутренние слои campaigns/identity, не читает и не пишет их таблицы: `campaign_id` в таблице communication — opaque TEXT **без** cross-context FK (подтверждено ownership-тестом).

## Application (`ChatService`, `MemberEventService`)

- `ChatService.send_message({campaign_id, author_id, client_message_id, content}) → {event, created}`:
  - членство проверяется сервером в каждой операции через `CampaignMembershipReader`; не-член → `NotAMember` (WS `forbidden`);
  - идемпотентность отправки: существующий `(campaign_id, client_message_id)` → replay того же события (`created=False`) без повторной рассылки; тот же `client_message_id` с другим автором → `ClientMessageConflict` (WS `conflict`);
  - присвоение `sequence`: `MAX+1` в этой же транзакции; коллизия PK (гонка двух записей) → `EventAppendConflict` → повтор до 3 попыток с новым sequence (арбитр — БД-ограничение, не Python-блокировка);
  - одна короткая транзакция (сервис) и `commit`; рассылку выполняет presentation **после** возврата сервиса, т.е. строго после commit.
- `MemberEventService.record_member_joined(campaign_id, member)` — вызывается адаптером campaigns: идемпотентен по `(campaign_id, member_guest_id)` (UNIQUE в БД); повторная доставка → replay без дубля и без рассылки.
- `ChatService.get_history(campaign_id, viewer_id, after_sequence=None, limit=200)` — member-only (`NotAMember`); события в возрастающем порядке; без `after` — последние ≤200 (новейший срез, возвращается по возрастанию), с `after` — все события с `sequence > after`.

## WebSocket-контракт (`communication/presentation/`, путь `/api/campaigns/{campaign_id}/chat`)

- **Handshake — до accept, в порядке**: (1) `Origin` из общего allow-list (`app.state.allowed_origins`; структурный `OriginAllowList` Protocol — тот же список, что для HTTP, отдельного списка нет); отсутствие/неразрешённый → close `4403`; (2) cookie-сессия через `identity.public.GuestResolver`; нет валидной → `4403`; (3) членство через `CampaignMembershipReader`; не-член (в т.ч. несуществующая кампания — без раскрытия существования) → `4403`. Только после всех проверок — `accept` и подписка на hub.
- **Клиент → сервер** (text frame, JSON): `{"type":"message","client_message_id":"<uuid>","content":"<строка>"}`; любой другой тип/форма → error `invalid_message`. Полей автора в кадре нет и не принимается — автор всегда гость из handshake-сессии (клиентскому полю автора не доверяем).
- **Сервер → клиент**: конверт `{"type":"message"|"member_joined","event_id","campaign_id","sequence","occurred_at", …}` с вложенным `message {id, author_id, author_nickname, client_message_id, content, created_at}` или `member {guest_id, nickname, role, joined_at}` (`event_to_wire`, один и тот же формат в WS и REST snapshot); replay → `{"type":"ack","event_id"}` без повторной рассылки; ошибки → `{"type":"error","code","detail"}`.
- **Коды ошибок WS**: `forbidden` (не-член при отправке; соединение закрывается `4403`), `invalid_message`, `conflict` (client_message_id занят другим автором), `retryable` (sequence не присвоился после повторов), `internal` (сбой persist), `delivery_failed` (сообщение сохранено, но не доставлено — соединение живо, история восстановится snapshot'ом).
- Отправка не-членом: членство перепроверяется сервером на **каждое** сообщение (снятие доступа между handshake и отправкой → `forbidden`, ничего не сохраняется).
- Два клиента одной идентичности: каждое соединение — отдельная подписка hub и получает каждое событие ровно один раз; повторная команда с тем же `client_message_id` дубля не создаёт (replay/ack).
- Событие `member_joined` появляется в потоке при вступлении гостя по приглашению (post-commit порт campaigns). Создание кампании организатором события не публикует — состав организатора приходит из `GET /api/campaigns/{id}` (базовый ростер), live-события — только новые присоединения.

## REST snapshot (member-only)

- `GET /api/campaigns/{campaign_id}/chat/events?after=<sequence>`: без валидной сессии → `403 forbidden`; не-член/несуществующая кампания → `403 forbidden` (без раскрытия существования, как у чат-WS; отличие от campaigns GET, где несуществующая кампания — `404`); успех → `200` `{"campaign_id","events":[<конверты>],"last_sequence"}`.
- Назначение: первичная история при монтировании и восстановление пропущенных событий после разрыва (cursor `after`); используется клиентским reconnect-протоколом (см. ниже §Фронтенд-срез и reconnect-протокол клиента, u4k.5).

### Состояние встречи (кандидат dunvyr-lbp.1)

Локальный кандидат, интеграция и независимое ревью ожидаются. К общим конвертам добавлен `type: "game_session_changed"` с `game_session_state: {revision, session}`; формат состояния и ACL команд — [campaigns](campaigns.md). Тот же поток и sequence используются для live и истории; миграция `0008` добавляет поля состояния/revision и UNIQUE `(campaign_id, game_session_revision)`. Каждый member-only snapshot чата дополнительно возвращает актуальный `game_session_state` независимо от курсора и ограничения последних 200 событий, включая пустую историю. Клиент объединяет REST и live по строго возрастающей revision, поэтому запоздавший ответ или replay не откатывает статус.

Событие встречи сохраняется в общей транзакции вместе с состоянием и receipt, в отличие от отдельного post-commit `member_joined`; notifier после commit перечитывает событие и рассылает его. Сбой staging/commit откатывает все записи без фантомного уведомления, сбой уведомления не отменяет commit; восстановление — через snapshot/reconnect, не гарантия exactly-once доставки. Граница владения и транзакции — [ADR](../../rules/architecture/adr/game-session-transaction.md). Integration-тесты `test_game_session.py` и `test_game_session_persistence.py` покрывают rollback, post-commit recovery, snapshot за пределами 200 событий и restart; результаты gate — в [campaigns](campaigns.md).

## Доставка строго после commit

- Сообщение: сервис коммитит → presentation рассылает событие в `RealtimeHub`. Ошибка доставки (упавшее соединение) — лог + `delivery_failed` отправителю; **сообщение остаётся сохранённым**, rollback нет.
- Фантомной доставки нет: рассылка выполняется только для `created=True` после успешного commit; сбой persist → ничего не рассылается (integration-тест с подменённым сбойным append).
- `member_joined`: `join_campaign` в campaigns **коммитит членство**, затем вызывает порт `CampaignEventPublisher.member_joined`; адаптер communication (`CampaignMemberJoinedPublisher`) **отдельной транзакцией** записывает событие в единый поток и рассылает его. Любая ошибка адаптера логируется и никогда не ломает уже закоммиченный join (порт вызывается после commit, исключения проглатываются с warning на стороне campaigns).
- `RealtimeHub`: внутрипроцессный реестр per-campaign очередей `asyncio` (thread-safe: `call_soon_threadsafe`; отправка сообщения выполняется в threadpool, рассылка — из event loop соединения). Без Redis/очередей — осознанное ограничение однопроцессного MVP.

## Инфраструктура и миграции

- Бизнес-миграция `0005` (после campaigns `0004`): одна таблица `communication_events` для обоих типов событий — `campaign_id` TEXT, `sequence` INTEGER, `event_id` TEXT, `kind` (`message`|`member_joined`), `occurred_at` TEXT (isoformat), поля сообщения (`message_id`, `author_id`, `author_nickname`, `client_message_id`, `content`) и поля участника (`member_guest_id`, `member_nickname`, `member_role`, `member_joined_at`); PK `(campaign_id, sequence)`; UNIQUE `event_id`, `(campaign_id, client_message_id)`, `(campaign_id, member_guest_id)`; индекс `campaign_id`. UUID/datetime — TEXT (isoformat), как в campaigns/identity; **без** FK в чужие таблицы.
- Зависимость backend: `websockets` (runtime, для реального WS в uvicorn); интеграционные тесты поднимают WS in-process через `TestClient` без сетевых портов и без этого пакета.

## Origin-состав (LAN-dev и E2E)

- Отдельного allow-list для WS нет — общий с HTTP `DUNVYR_ALLOWED_ORIGINS` (`app.state.allowed_origins`): dev (`make dev`/`scripts/dev.sh`) — `http://<LAN-IP|localhost|127.0.0.1>:5173`; E2E (Playwright `webServer`) — `http://127.0.0.1:5273` (порты 8100/5273 отличаются от dev 8000/5173). Браузер подключается к WS same-origin через Vite-прокси `/api` с `ws: true`, поэтому `Origin` handshake = origin фронтенда; не-браузерный клиент без `Origin` → отказ (как HTTP `require_allowed_origin`).

## Архитектурные контракты

- Добавлены 4 контракта communication (по образцу identity/campaigns): слои `presentation > application > domain` и `infrastructure > application > domain`; запрет `communication.public` импортировать внутренние слои; запрет `communication.domain` импортировать внешние слои. Итого **16** контрактов, все зелёные.
- Табличный ownership-тест (`test_communication_tables.py`): metadata communication содержит только `communication_events` (префикс `communication_`); PK `(campaign_id, sequence)`; UNIQUE `event_id`, `(campaign_id, client_message_id)`, `(campaign_id, member_guest_id)`; `campaign_id` без foreign keys (opaque TEXT).
- Unit-тесты архитектуры фиксируют единственные межконтекстные импорты communication — `identity.public` и `campaigns.public` (два отдельных теста); integration-тест фиксирует неизменность строк `campaigns_*`/`identity_*` вокруг чат-операций (WS-отправка, replay, snapshot).

## Фронтенд-срез (ChatPanel) и reconnect-протокол клиента (u4k.5)

- `ChatPanel` размещён в `CampaignScreen` **до** секций приглашения и участников (mobile-приоритет: чат — основной элемент, DOM-порядок + адаптивный CSS `index.css`). Состав: статус соединения (`connecting/open/reconnecting/closed/error`, `aria-live`), поток `<ol>` (свои сообщения — «Вы» + визуальное отличие `chat__message--own`, чужие — псевдоним автора; `member_joined` — системная строка «N присоединился к кампании»), поле ввода `textarea` (maxLength 2000) + «Отправить», ошибки с `aria-live="assertive"`. Статусы честные: `connecting` «Подключаемся к чату…» (loading), `reconnecting` «Соединение с чатом потеряно. Восстанавливаем…» (stale), `closed` после исчерпания окна «…Восстановить не удалось. Обновите страницу.» (offline), `error` — ошибка соединения.
- История: после каждого WebSocket open, включая первый, выполняется snapshot; первый запрос без курсора возвращает последний срез. Все новые `member_joined`, включая первичный snapshot, передаются ростеру (дедупликация по `guest_id`). `chat.ts` дедуплицирует по `event_id` и сортирует по `sequence`.
- **Протокол транспорта:** сервер после авторизации подписывается на hub до `accept`, отписка выполняется также при ошибке accept. Клиент буферизует live-кадры до завершения snapshot, не объявляет open и не отправляет сообщения во время восстановления. При разрыве/ошибке буфер отбрасывается, сокет закрывается, запрос отменяется и запускается следующая попытка.
  - Первая попытка и каждое восстановление ограничены 30 с общего времени, каждая handshake+snapshot попытка — 5 с; не более 5 повторов с задержками 500/1000/2000/4000/8000 мс. При исчерпании — `closed`; размонтирование отменяет таймеры и запрос. Устаревшие callbacks и завершения игнорируются.
  - Курсор подтверждается только фактически полученными событиями snapshot, не live-событиями и не отдельно прочитанным `last_sequence`. После пустого начального snapshot следующий запрос использует `after=0`; при последующих запросах `after` равен максимальному sequence событий snapshot. События объединяются по `event_id`.
- Отправка: `client_message_id` генерируется клиентом (`createIdempotencyKey`); повторная отправка/двойной клик не создают дубль (серверный replay → `ack`). Optimistic UI нет: при неоткрытом сокете `sendMessage` возвращает `false` и показывается «Чат не подключён. Сообщение не отправлено.». Транспорт инжектируется (`ChatTransportFactory`) — в unit-тестах управляемый стаб/FakeWebSocket вместо нативного `WebSocket` (jsdom его не имеет; обоснованный implementation-coupled substitute).

## Проверки на введённом снимке

u4k.4: `make lint`, `make test-unit`, `make test-integration` зелёные (исполнитель и координатор независимо, одинаковые байты кандидата; после repair-раунда M1 — координатор на обновлённом снимке): **170** backend unit (+27 к u4k.3: communication — домен 10, service 7, architecture 4, tables 4; campaigns service +2 — порядок «commit → publish» и отсутствие повторной публикации при replay), **16** import-контрактов, **39** frontend Vitest (+8: `ChatPanel` 6 — отправка/поток/свои-чужие/дедуп, `CampaignScreen` — live-ростер и mobile-порядок), **73** integration (+12: `test_communication_chat` 11 — broadcast всем подключённым, доставка строго после commit (сбой persist без рассылки; сбой доставки при сохранённом сообщении), handshake-негативы (нет сессии/чужой Origin/не-член → отказ), отправка не-членом → `forbidden` без записи, два клиента одной идентичности без дублей, `member_joined` live + персистентность в одном потоке, неизменность строк `campaigns_*`/`identity_*` вокруг чат-операций; `test_communication_persistence` 1 — сообщения переживают «рестарт» двумя экземплярами приложения). E2E smoke 2 (desktop+mobile) зелёный, сценарий не менялся. TDD: домен — наблюдаемый RED `8 failed, 2 passed` → GREEN; service — RED `7 failed` → GREEN.

u4k.5 repair, локальный кандидат, интеграция и независимое ревью ещё ожидаются: `RUN=u4k5repair make lint` exit 0; `make test-ci` exit 0 — 170 backend unit, 16 import contracts, 52 frontend tests, 77 integration, 4 E2E desktop/mobile. Тесты проверяют initial barrier, cursor, отмену/таймаут и cleanup неудачного accept. E2E проверяет двух гостей и reload, а не автоматический обрыв соединения в браузере.

## Ограничения (ещё не существует)

- Reconnect-окно ограничено 5 повторами / 30 с общим deadline (u4k.5): после исчерпания — честный offline с предложением обновить страницу; бесконечного фонового retry нет. События между разрывом и успешным восстановлением доставляются resync-snapshot'ом по курсору `after`.
- narration/NPC-типов сообщений нет (только базовые визуальные типы `message`/`member_joined`); журнал, TTS, presence online/offline, исключение участника (kick) — поздние вехи.
- **Блокировок речи по состоянию персонажа нет**: персонажей не существует (вехи 3+); когда появятся, проверка возможности говорить должна быть серверной в точке приёма сообщения.
- Rate limit на WS-отправку сообщений не введён (вне критериев этой задачи; HTTP-лимиты identity/campaigns сохраняются) — кандидат на отдельный ограниченный follow-up.
- `member_joined` идемпотентен по `(кампания, гость)` — одно событие на вступление; будущий kick + повторный join потребуют пересмотра уникальности. Организатор при создании кампании событие не получает.
- `RealtimeHub` и rate-лимитеры — per-process: multi-worker uvicorn не поддерживается (однопроцессный MVP).
- Snapshot без `after` ограничен 200 последними событиями; пагинация глубже не предусмотрена (нет UI-потребности в MVP).
- Мобильное поведение «клавиатура не скрывает ввод» обеспечено DOM-порядком и адаптивным CSS; мобильный E2E чата существует с u4k.5 (сквозной сценарий двух гостей в `smoke-mobile` — эмуляция устройства в Chromium, [tooling/commands](../tooling/commands.md)); само поведение клавиатуры реальным мобильным E2E не проверяется.
