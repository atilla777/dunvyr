# Очередь небоевого испытания

Кандидат `dunvyr-lbp.4`, проверенный в собственной worktree; независимое ревью и интеграция ожидаются. Продуктовые требования — [gameplay](../../product/gameplay.md) и [presence](../../product/multiplayer-and-access.md#presence-и-отключения); границы владения и транзакции — [ADR](../../rules/architecture/adr/encounter-runtime-queue.md). Ниже описан кандидат, не утверждение о публикации в main.

## Состояние и переходы

`gameplay` хранит в SQLite один runtime на кампанию, а не на объект или встречу. Доступный неизменяемый шаблон принадлежит `adventures`; runtime сохраняет его ID, не полный шаблон. Начать может участник с собственным допустимым сохранённым персонажем при running-встрече. На старте фиксируются все участники с допустимыми персонажами, включая offline, в порядке `(joined_at, guest_id)`; поздние участники и персонажи в эту очередь не добавляются. Несколько вкладок не создают дополнительные слоты.

Текущий online-игрок может обменяться с более поздним непройденным online-слотом этого раунда. Обмен не расходует действие и не добавляет ход; базовый порядок восстанавливается в следующем раунде. Текущие offline-слоты автоматически пропускаются без наград после учёта окна presence; переподключение не возвращает сохранённый пропуск. Если все offline, текущий раунд исчерпывается и ждёт; при появлении участника создаётся максимум один следующий раунд за нормализацию. Пауза и завершение встречи замораживают переходы; resume либо новая running-встреча продолжают тот же runtime с последующей нормализацией. После рестарта runtime сохраняется, presence начинается пустым и текущий раунд может быть исчерпан при восстановлении.

Фоновый проход периодически сверяет сохранённые очереди даже без HTTP-запросов; ошибка одной кампании логируется и повторяется на следующем проходе. Ограничение среза: исполнения действия, ручного пропуска, предложений, бросков, резолюции, эффектов, AI и боя здесь нет; нельзя завершить испытание или запустить другое поверх существующего runtime.

## HTTP-контракт

Все пути ниже относительны `/api/campaigns/{campaign_id}/queue`; требуется cookie-сессия и членство. `GET` возвращает `Cache-Control: private, no-store` и `{version, queue}`; до старта это `{version: 0, queue: null}`. Иначе `queue` содержит `encounter_id`, `participants: [{guest_id, character_id}]` в базовом порядке, `round_order` (ID гостей), `round_number`, `cursor`, `skipped` (ID гостей), `current_guest_id` (ID или null). `version` монотонна для кампании.

`POST /start`: строгий JSON `{expected_version, expected_lifecycle_revision, character_id, encounter_id}`; версии — целые числа не ниже 0, ID персонажа — UUID, ID испытания — строка длиной 1–128. `POST /swap`: `{expected_version, expected_lifecycle_revision, target_guest_id}`; версия очереди не ниже 1, revision не ниже 0, ID — UUID. Лишние поля запрещены. Обе команды требуют разрешённый `Origin`, UUID-заголовок `Idempotency-Key` и проходят отдельный per-process rate limit. Ответ — состояние и `replayed`; start возвращает 201 при создании и 200 при replay, swap — 200. Успешные ответы также `private, no-store`.

Одинаковые актор, кампания, ключ и payload возвращают исходный сохранённый ответ, даже если состояние уже изменилось; повтор ключа с другим payload — 409 `conflict`. Ошибки: 403 `forbidden` для отсутствия доступа или недопустимого Origin, 403 `invalid_character`; 409 `stale_lifecycle`, `meeting_not_running`, `stale_state`, `invalid_action`, `invalid_swap` или `encounter_unavailable`; 422 для некорректных DTO/UUID/заголовка; 429 с `Retry-After` при ограничении частоты. Доступ проверяется сервером, а не только интерфейсом. Секреты сценария в проекцию очереди не включаются.

## Конкурентность и доставка

Публичный порт campaigns берёт DB writer lock до чтения lifecycle и ростера; owning adapters используют одну транзакцию. Версия очереди защищена DB CAS/уникальностью, команды также проверяют lifecycle revision. Короткий presence guard удерживается от снимка до commit в порядке DB → presence, без сети внутри. Состояние, receipt и событие `queue_changed` фиксируются атомарно; уведомление отправляется только после commit, его сбой не откатывает состояние. Полный snapshot и live-доставка описаны в [communication](communication.md); доставка best-effort, восстановление из snapshot, не exactly-once.

## Проверки кандидата и ограничения доказательств

На fingerprint кандидата `84c695d7aae1286b7fa4db11cfa331c7362441b4e56b84b1fc0940a32d42f2b5` (SHA-256 полного manifest, base `8af4569446bc49b780dfa6002949bfd09218af88`) исполнитель сообщил успешные `make lint` и `make test-ci`: 316 backend unit, 31 import contracts, 84 frontend, 199 integration, 14 desktop/mobile E2E. `test_gameplay_domain.py` проверяет доменные переходы; `test_gameplay_security.py`, `test_gameplay_concurrency.py`, `test_gameplay_lifecycle.py`, `test_gameplay_presence.py`, `test_gameplay_worker.py` и `test_gameplay.py` — API, конкурентность, lifecycle, presence и восстановление; `QueuePanel.test.tsx` и `e2e/queue.spec.ts` — UI. Это результаты локального кандидата, не интегрированного gate и не приёмка на реальном телефоне/LAN.
