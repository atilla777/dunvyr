---
name: mis-proj-op-beads
description: >-
  Read, reconcile, create and update native Beads Epic/Task/Bug records and blocks
  in a prepared MIS project, with bounded writes and separate verified Dolt
  publication; conditionally claim, link and complete one Task/Bug, checking its
  parent Epic on substantive criteria. Not project initialization or implementation.
---

# Native Beads — фиксированная операция MIS

Если требуется общение непосредственно с пользователем, до вопроса, обсуждения
решения или сообщения о проблеме загрузи `mis-proj-lib-common` и его
`references/dialogue.md`. При внутреннем вызове верни факты caller; не начинай
второй диалог вместо координатора.

Caller задаёт существующий project root, разрешённую операцию, поля/область,
ожидаемые типы/ID и результат. Здесь нет feature lifecycle, adapters или config
resolver. Поддерживаемый проверенный baseline — `bd` 1.3.1. Перед первым действием
проверь `bd version`, `bd -C <root> where`, `bd -C <root> context --json`,
`bd -C <root> dolt status` и help нужных команд; повторяй при смене среды.
Workspace должен принадлежать выбранному проекту, не ambient/global database.
Отсутствующая, redirected без доказанной принадлежности, read-only или недоступная
БД блокирует запись. Не запускай init/bootstrap/install/migration и не обходи
через `--global`, `--db`, `--database`. Не редактируй внутреннее хранилище.

CLI запускай безопасными отдельными аргументами, проверяй exit code **и** полный
JSON. Тексты передавай quoted arguments или `--body-file`. Truncated/malformed,
неизвестный формат и ошибка — не пустой результат. Извлеки сохранённый полный
вывод или сообщи неполноту. Повторно используй checked capabilities в том же
контексте, не читай help для каждой записи.

## Чтение и отсутствие дублей

Все команды ниже — `bd -C <root> --readonly …`:

| Что | Команда |
| --- | --- |
| Полный inventory | `list --all --limit 0 --max-rows 0 --include-gates --include-ephemeral --include-infra --include-templates --brief --json` |
| Полные собственные поля точного ID | `show <id> --brief-deps --json` |
| Все прямые дети | `list --parent <id> --all --limit 0 --max-rows 0 --include-gates --include-ephemeral --include-infra --include-templates --brief --json` |
| Blocked → prerequisite | `dep list <blocked> --type blocks --direction=down --json` |
| Child → parent | `dep list <child> --type parent-child --direction=down --json` |

Inventory/list и show — массивы; show требует ровно один точный ID, проверенный
actual type/status/assignee. Brief не содержит description/acceptance/notes:
omitted не означает empty. Для смыслового сравнения прочитай полные поля всех
релевантных кандидатов, включая закрытых и находящихся вне выбранного Epic.
Unknown type не отбрасывай как «не работа» без проверки. Сохрани его контекст,
но не преобразуй в Task. Exact ID можно читать без общего inventory, если не
нужно доказывать отсутствие дублей. Parent не выводится из dotted ID.

Native edges могут содержать related `id` + `dependency_type` либо
`issue_id`, `depends_on_id`, `type`. Нормализуй по queried ID и направлению;
unknown shape — пробел. Membership `parent-child` не является `blocks`.
Внешние blocker/ancestor paths читай по точным ID с visited set; для cycle check
не ограничивай граф детьми одного Epic.

## Ограниченные записи и read-back

Перед remote-gated записью прочитай [publication](references/dolt-publication.md)
и проверь destination, полномочия на shared history, sandbox/hooks и возможность
публикации. Полное поручение может разрешать публикацию своих изменений, но не
произвольной соседней истории. Не меняй remote/config/hooks, чтобы обойти отказ.
Обычные записи всегда `bd -C <root> --sandbox …`: sandbox отключает bd auto-push,
но не hooks, concurrent writers или локальные commits.

Перед каждой записью заново прочитай ID/type/status/assignee, изменяемые поля и
нужные edges/parent. Не перезаписывай чужой claim, спорные изменения или историю.
Запись ограничивай согласованными полями. После — отдельно `show` и relevant
typed edges/child selection; проверь как новые, так и сохранённые поля.

- **Create:** сначала all-status смысловое reconciliation по цели/источникам/
  границам/parent и устойчивой идентичности из запроса. Existing exact match →
  reuse ID; ambiguous → conflict. Никаких обязательных MIS keys/registry.
  `create --type epic|task|bug --title <text> --description <text> --acceptance <text> --json`;
  optional `--parent <confirmed-open-epic>`. Для Bug нужны actual/expected/repro:
  дефект либо явно обозначенный запрос нового поведения с текущим/желаемым
  сценарием. Недоступные факты помечай неизвестными, не выдумывай; неполное
  сообщение сохраняется с пробелами, без заявления готовности к run.
  Ответ — object с ID; проверь show, membership и повтори поиск collisions.
  Родитель только epic; standalone не требует фиктивного parent/spec/design.
- **Update:** `update <exact-id> --description … --acceptance … --json` (лишь
  нужные поля; ответ — array). Сравни свежие expected values, сохрани чужую прозу,
  ссылки, notes, статус и assignee. Применяй `--if-status`/`--if-assignee` по
  проверенному состоянию: они не защищают произвольный текст от lost update.
  Для append используй `--append-notes`, не replay целого notes. Не делай
  multi-ID update, status/claim/close или type conversion при планировании.
- **Membership:** create с `--parent` либо разрешённый `update <child> --parent
  <epic>`. Проверь open Epic, child, ancestry/cycles; после — parent-child edge
  и unlimited children. Reparent/removal меняют scope и требуют явной причины
  и полномочия; не двигай начатую/чужую работу молча.
- **Blocks:** `dep add <blocked> <prerequisite> --type blocks --json`. Проверь
  оба endpoint/type/status/ownership, смысл причины, внешние paths и циклы.
  Cross-Epic/standalone допустимы при известной разрешённой области; принадлежность
  внешнего blocker не даёт права его редактировать. Существующий exact edge →
  no-op. Не используй `--no-cycle-check`. После — отдельно проверь направление.
  `dep remove <blocked> <prerequisite>` только при разрешённом точном удалении,
  свежем подтверждении типа/направления и последующей проверке отсутствия.

Read/write/read не является universal CAS, search не гарантирует уникальность
при concurrent creates, external-ref не unique. Не требуй глобальных locks, но
если явно нужна более сильная гарантия, останови зависимую запись при отсутствии
native поддержки. Stale guard/неожиданное изменение → reconciliation, не force.
При неизвестном эффекте сначала перечитай состояние; не повторяй create/append
вслепую. При частичном сбое верни все сохранённые ID/поля/edges и точный остаток.

## Публикация и граница

Для выбора/claim/возобновления внутри `mis-flow-run` сначала прочитай
[references/execution.md](references/execution.md). Это отдельная разрешённая
область S3; запрет status/claim при **планировании** выше остаётся в силе.

Публикация — отдельная операция по [references/dolt-publication.md](references/dolt-publication.md).
Не считай локальный write/commit, Git push или exit 0 доказательством remote
Beads. Верни `ok|blocked|conflict|error`, фактические ID/дельту, проверенные поля/
edges, completeness/limits и отдельный receipt remote revision. Завершение exact
Task/Bug, проверка Epic и recovery — только по [references/completion.md](references/completion.md)
и явному поручению run flow; планирование не закрывает записи. Не начинай
реализацию кода и не запускай следующую работу.
