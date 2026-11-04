# Отдельная публикация Beads/Dolt

Только при publication или remote-gated write preflight. Это не Git push и не
операция над одной записью: отправляется **общая история** проекта. Проверенный
baseline: bd 1.3.1, embedded Dolt, native dolt 2.4.1, branch main.

## Проект, destination и полномочия

1. По `bd where`, `bd context --json`, `bd dolt status`, `bd dolt remote list`
   проверь проект/engine/remote name+address. Из observed engine metadata найди
   database child с `.dolt`: status может называть только контейнер. В verified
   embedded database выполни `dolt status`, `dolt branch -av`, `dolt remote -v`.
   Не угадывай child по prefix и не запускай native CLI в live server data dir.
   Другой engine/branch требует доказанного безопасного mapping; иначе blocker.
2. Для новых записей с обязательной публикацией и для push установи полномочия
   на shared main history в выбранный destination: standing policy потребителя
   либо явная область поручения. Запиши источник полномочий в результате.
   Соседняя история должна быть покрыта; claim/Epic/status этого не доказывают.
   Нет покрытия → точный scope blocker, не формальный вопрос на каждый ID.
   Не переноси политику репозитория MIS в потребителя автоматически.
3. Для preflight проверь sandbox support, hooks/другие auto-publication routes,
   destination и доступность remote. Повторно используй эти проверки до смены
   среды/политики/hooks. Перед реальным push остаются свежие проверки ниже.

Не настраивай remote/upstream, не делай скрытый pull/merge/reset/checkout,
force, `--yes`, push `--all`, deletion или raw SQL. Native CLI здесь используется
лишь для Dolt VCS, не обхода bd при записи records. Не требуется отдельный clone,
private ref, lock, полная историческая построчная экспертиза или файл receipt.

## Сначала подтвердить, потом отправлять недостающее

Различай требуемый revision **S**, текущий local main **L** и свежий выбранный
remote main **R**. Для нового результата наблюдай L как candidate S после
read-back записей. Для recovery восстанови точный S по доступным фактам/history;
не заменяй известный S более новым L. Неизвестный S блокирует подтверждение.

В verified database:

1. `dolt fetch --silent <remote>`; `dolt branch -av` — проверь полные L/R и точные
   refs. `dolt merge-base <S> <R>` равен S (либо S=R после fetch) → S reachable:
   **verified no-op**. Проверяй это раньше clean/local-direction/new-write gates:
   более новая или грязная local copy не мешает подтвердить старый результат.
   Fetch/ref/ancestry error или ambiguous output — unknown, не «S отсутствует».
2. Только успешный unambiguous merge-base, отличный от S, доказывает отсутствие S
   в R. Тогда заново проверь scope/authority/destination, committed clean working
   set (`dolt status`), S reachable from L и направление `merge-base <L> <R>`.
   R ancestor of L → допустим outgoing; incoming-only/divergence → conflict,
   никакого тихого merge. Pending writes не коммить молча: верни точный blocker.
3. Непосредственно перед push вновь проверь main/L/scope, сохранив S. Выполни
   только `dolt push --silent <remote> main:main`. Это moving shared branch,
   не atomic snapshot/CAS: concurrent authorized commits могут попасть в push.
4. Независимо от ответа push снова fetch выбранного remote, прочитай свежий R
   и докажи S reachability. Cached tracking ref или exit 0 недостаточны.

При rejected/timeout/nonzero push сначала подтверждай S, а не повторяй команду.
Если S уже reachable — успех без replay. Если доказанно отсутствует — допускается
только недостающая отправка после свежих direction/scope checks. Unknown остаётся
unknown; divergence — conflict. Не повторяй create/update, чтобы чинить push.

Верни `ok|blocked|conflict|error`, project/database, remote/address/branch,
authority source, IDs и local facts отдельно от S/L/свежего R, ancestry evidence,
push attempted/confirmed/no-op, limits и остаток. `ok` только после свежего remote
подтверждения. Гарантия — reachability S из R, не приемка более поздней работы и
не доказательство побайтовых полей remote; локальные поля проверяются отдельно.
Операция не записывает/закрывает issues и не публикует Git.
