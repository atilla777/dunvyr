# Завершение одной Task/Bug и проверка Epic

Только по поручению `mis-flow-run`, после основного read/write/read-back протокола.
Читай [dolt-publication.md](dolt-publication.md) до remote-gated writes: полномочия
должны покрывать shared outgoing history, не только выбранный ID. Проверенный
baseline `bd 1.3.1 close --help`: exact ID и `--reason`, но **нет** status/assignee
CAS guards у close. Не выдумывай их и не заменяй close на raw storage write.

## Сначала результат, затем close, затем отдельная публикация

1. Получи подтверждённый Git receipt: remote URL/ref, sent S/tree, fresh R и
   ancestry, tests/review exact snapshot, spec/no-op. Git-result должен покрывать
   собственные критерии Task, не просто «push exit 0». Для подтверждённой
   non-Git/local-only работы нужны реальные проверенные результаты и объяснение
   исключения, не фиктивный SHA. Неполное обязательство блокирует close.
2. Fresh exact show/parent/blockers: Task/Bug, `in_progress`, свой assignee,
   единственный writer, выполненные acceptance/constraints. Сохрани bounded result
   через guarded `update --append-notes` из execution protocol: Git destination/
   S/tree, checks/review provenance, spec paths/no-op, выполненные criteria и
   ограничения. Не называй Dolt опубликованным заранее. Equivalent notes → no-op,
   unknown append → read-back до retry.
3. Перед close ещё раз show/typed edges. Выполни ровно
   `bd -C <root> --sandbox close <exact-id> --reason <bounded-result> --json`.
   Нельзя multi-ID, empty ID, `--force`, `--continue`, `--claim-next`, reopen или
   обход gate. Native close не universal CAS: при реальном concurrent writer,
   требующем более сильной гарантии, остановись. Перечитай status, close_reason,
   assignee, notes и остальные поля/edges. Ошибка/timeout → сначала show; closed с
   нужным result — no-op close, несогласованный closed — conflict, не переписывать.
4. Если есть Epic, прочитай его **собственные** description/acceptance, все прямые
   дети all-status/unlimited и их точные поля, parent/blockers и актуальный
   реализованный результат. Required children должны быть действительно выполнены;
   cancelled/deferred/unknown не равно выполнено. Не исполняй следующий child.
   Все дети closed **не достаточно**: сопоставь собственные критерии вехи с
   реальными tests/spec/remote evidence. Не хватает evidence → оставь Epic открыт,
   укажи остаток (успех Task от этого не пропадает). Не делай новый scope под видом
   проверки. При закрытии Epic нужны права на exact Epic, отсутствие foreign claim,
   gates/blockers и свежие own criteria/children. Сохрани evidence bounded append
   с guards актуального status/assignee, затем exact close/read-back как выше.
   Уже закрытый Epic — проверь факты, не reopen/reclose автоматически.
5. После всех нужных writes наблюдай required Dolt revision **S** из verified
   committed local main; read-back exact records обязателен. По отдельному
   publication resource подтверди S reachable из свежего remote R либо отправь
   только недостающее. Публикация общая, Git SHA не Dolt revision. Local close
   остаётся фактом при отказе/unknown Dolt push; не reopen и не повторяй writes.

## Recovery — exact ID, без новой работы

- **Git опубликован, Task открыт:** восстанови S/tree/destination/checks/review
  из notes/сессии/истории и fresh Git remote. Reuse прежнюю worktree, без claim
  заново/implementation/recommit/push, если ничего не недостаёт. Неизвестная связь
  или недостаточные checks остаются blocker. Выполни result/close/Epic/Dolt часть.
- **Task закрыт, Dolt не подтверждён:** closed допускается только как explicit-ID
  completion recovery; не ready selection/claim/reopen. Проверь результат/own
  acceptance и Git receipt, восстанови exact требуемую Dolt S из history/session.
  Если S потерян, current committed L можно выбрать **новым** required revision
  лишь после fresh read-back всех требуемых полей/результатов и проверки authority
  на его shared scope; не называй его прежним S. Не повторяй append/close.
- **Оба канала подтверждены:** confirmation-only no-op, без create/новой worktree,
  switch, лишних commits/push/close. Чужой dirty local state не мешает подтвердить
  прежний snapshot, но не включается в него. Неизвестный результат — точный остаток,
  не успех. Новые после close изменения Task/графа не прячь за старым receipt.

Верни отдельные local Task/Epic facts, Git receipt, Dolt S/L/fresh R/destination,
authority и результат confirmation/push. Task completed локально, Git published и
Beads published — три разных факта. Не создавай обязательный receipt/handoff файл.
