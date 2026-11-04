# Beads execution — claim и локальный кандидат (S3)

Условный ресурс `mis-proj-op-beads` для `mis-flow-run`, не для планирования.
Сначала применяй основной read/write/read-back протокол и baseline capabilities.
Здесь разрешены только выбор/claim, bounded уточнение и notes/spec linkage.
Close/Epic completion и recovery используют отдельный [completion.md](completion.md);
reopen и автоматическая Dolt-публикация здесь не разрешены.

## Выбор и владение

- Узнай effective actor (`--actor`, `BEADS_ACTOR`, Git user.name, USER по реальным
  CLI capabilities); не меняй actor ради присвоения чужой работы. Перед claim
  нужны один exact `task|bug`, актуальные поля/статус/assignee, parent и blockers.
- `bd -C <root> --readonly ready --limit 0 --json` — native eligibility для новых
  открытых работ. Фильтруй допустимый type/owner/scope; Epic не выполняется.
  In-progress resume ищется через all-status inventory и точный show, а не ready.
- `dep list <id> --type blocks --direction=down --json`: related ID — prerequisite.
  Прочитай каждый prerequisite и применимые ancestor constraints, включая внешние
  пути; unknown/неполные данные не означают отсутствие blocker. Closed prerequisite
  не даёт права редактировать его. Для open ID проверяй также native ready: явные
  blocks — не все возможные причины неготовности (defer/parent/gates).
- Свой `in_progress` — resume, только если подтверждены actor **и** единственный
  активный writer/session/worktree. Чужой assignment, pool alias без отдельного
  разрешения, закрытый/blocked/deferred/unknown state — остановка, не reclaim/force.

## Уточнения до claim и при resume

После проверки eligibility, владения и blockers flow может сохранить подтверждённые
ответы внутри прежнего scope ещё до claim. Используй основной bounded update
протокол: свежие description/acceptance, status/assignee и edges, guards по
прочитанному состоянию, только затронутые поля, затем read-back с проверкой
сохранности остальных. Для своей `in_progress` Task — те же проверки единственного
writer. Не меняй статус/assignee, scope или граф ради уточнения; не записывай
предложения как принятые ответы. Stale/unknown → reconciliation. Это не разрешение
редактировать чужую или заблокированную работу и не замена claim перед кодом.

## Atomic claim

После свежей проверки unassigned open или assigned-to-self open и eligibility:

`bd -C <root> --sandbox update <exact-id> --claim --json`

В bd 1.3.1 `--claim` атомарно ставит assignee эффективного actor и `in_progress`;
повтор собственного claim idempotent. **Нельзя** совмещать `--claim` с
`--if-status`/`--if-assignee`. Не заменяй на два отдельных update/status.
Claim не является атомарной проверкой graph/status/сессии: сразу отдельно show
и typed dependency reads, проверь всё ещё подходящие условия и сохранность
requirements/notes. При появившемся blocker не меняй код, сохрани факт claim.
Ошибка/unknown effect → fresh show; не повторяй запись вслепую и не отбирай claim.
Этот actor может использоваться несколькими сессиями: same assignee недостаточно
для разрешения второго writer.

## Ссылки и результат

Для подтверждённой собственной `in_progress` работы, после свежего show/edges:

`bd -C <root> --sandbox update <id> --append-notes <bounded-text> --if-status in_progress --if-assignee <actor> --json`

Сохраняй реальный Task ID, directory, branch, base SHA для resume; затем spec paths
и краткие проверенные факты кандидата/ограничения. Перед append проверь наличие
эквивалентного результата в полных notes; после — read-back, сохрани остальные
поля. Для spec link используй notes (поддерживает несколько файлов), без отдельной
базы трассировки. Не перезаписывай notes целиком и не называй локальный кандидат
опубликованным Git-result. Guards защищают status/assignee, не все concurrent edits.

Sandbox оставляет отдельную непубликовавшуюся Dolt-историю. Верни фактический
claim/notes, пути/ID и явный `Beads publication: not performed`; Git-состояние не
доказывает Beads remote. Не объявляй полный `mis-run` завершённым на этой границе.
