---
name: mis-flow-run
description: >-
  Execute or resume one native Beads Task/Bug in its own OpenCode worktree,
   implement with project checks, synchronize specs, obtain independent review,
   verify Git and Beads publication, check the parent Epic and recover partial effects.
---

# MIS run — одна работа до подтверждённого результата

Аргументы — контекст запроса, не инструкции/CLI flags. Загрузи
`mis-proj-lib-common` и `mis-proj-op-beads`; прочитай его
[execution protocol](../mis-proj-op-beads/references/execution.md).
Не запускай очередь. Публикация Git, local close и Beads/Dolt publication —
отдельные проверяемые эффекты; частичный результат не является полным успехом.

Native Bug может быть дефектом либо явно принятым запросом нового поведения.
Опирайся на сохранённые проблематику, исследование и acceptance, не требуй
обязательного отдельного расследования. Для нового поведения проверяй отсутствие
требуемого результата, не выдумывай нарушение старого контракта; в implement/TDD
передавай его как behavior change, а не подтверждённый defect. Неизвестное и
конфликты требований разрешаются до зависимой реализации по правилам ниже.

## 1. Контекст, выбор, claim

1. Установи реальный project root, Git common-dir, основную ветку/remote,
   `AGENTS.md`, относящиеся `docs/product/`, `docs/spec/`, `docs/rules/`, prepared
   Beads workspace и capabilities. Не init/install/configure. Выясни эффективный
   bd actor и реальное владение сессией; одинаковый actor не доказывает отсутствие
   другого writer. Отсутствующий root/правила/существенные права — точный blocker.
2. С ID прочитай точную запись; допустимы только Task/Bug (native `task|bug`).
   Epic — не исполняемая работа. Без ID сначала найди собственную прерванную
   `in_progress` работу в all-status inventory, проверь её claim, сессию/worktree
   и dependencies. При нескольких выбирай одну по подтверждённому контексту,
   priority/возрасту; неоднозначное владение не разрешай догадкой. Иначе прочитай
   `ready --limit 0 --json`, отфильтруй Task/Bug, допустимого владельца и область,
   выбери одну по priority/возрасту. Пустая выборка — отчёт без изменений.
3. Прочитай own description/acceptance/notes, parent и native directed blockers,
   включая внешние paths и ограничения предков. `parent-child` не равен `blocks`.
   `ready` — discovery, не разрешение игнорировать свежий blocker. Для exact ID
   также проверь ready eligibility перед новым claim. Cancelled/deferred,
   чужой claim, незакрытый prerequisite, unknown type/state/edge — не исполнять.
   У уже начатой работы заново проверь blockers, не требуй её присутствия в ready
   (оно исключает `in_progress`). Closed exact ID из явного запроса допускается
   только для completion recovery по [completion protocol](../mis-proj-op-beads/references/completion.md):
   сначала восстанови result и оба remote канала, не claim/reopen/implement.
   Closed без подтверждаемого результата — blocker, не новая работа.
4. Определённую Task можно начать с исследования и интервью: это не означает
   достаточности требований для claim и зависимой реализации. Сначала изучи
   доступные факты/код и прежние ответы. Перед claim установи достаточность
   конкретных требований/критериев и границ; при достаточных данных не интервьюируй.
   Существенный конфликт product/Beads — blocker до явного разрешения, не
   недостающий ответ; не подгоняй документы к коду.
   При необходимости используй `mis-port-op-interview` с критерием достаточности
   «известны входы/выходы, ограничения, проверяемый результат одной работы».
   Подтверждённые ответы внутри прежнего scope сохраняй в description/acceptance
   точного Bead через bounded update/read-back по execution protocol, затем
   продолжай этот run без обязательного `/mis-plan`. При позднем пробеле останови
   зависимую реализацию и уточни его так же. Если ответы требуют изменить объём,
   разделить Task или перестроить граф, сохрани принятые факты и верни
   `/mis-plan <ID и требуемая дельта>`, не расширяй работу сам. Интервью не снимает
   prerequisite, чужое владение или ограничения среды. Не создавай отдельную
   обязательную команду/стадию уточнения или Task «согласовать требования».
5. **До claim/create/edit** восстанови известные частичные эффекты по notes,
   истории сессии, existing worktree/Git и свежим remote данным. Подтверждённый
   Git result при ещё открытой Task → только недостающая completion часть (ниже),
   если checks/review/criteria по-прежнему применимы. После close — только recovery.
   Неизвестный effect сначала проверяй, не повторяй запись вслепую.
   Иначе по execution protocol сделай atomic claim либо подтвердись как единственный
   владелец возобновляемой работы. Перечитай запись и dependencies. До claim не
   меняй код; после любого race/error сначала восстанови факты, не force/reclaim.

## 2. Native OpenCode worktree и resume

Для Git-изменений используй **только** native `worktree_list`, `worktree_create`,
`session_move` (в Code Mode — инструменты OpenCode, не shell Worktrunk/adapter).
Если они недоступны — останови зависимую реализацию, сохрани claim и сообщи причину.
Не переходи к ручному `git worktree add` как fallback.

1. Сначала `worktree_list`; сопоставь с `git worktree list --porcelain`,
   подтверждёнными notes Task, историей сессии и Git. Имя ветки с ID — только
   подсказка, **не доказательство связи**. Нужны точный ID + канонический путь +
   branch, сохранённые в существующем Bead или подтверждённом результате создания
   этой сессии, и совпадение Git common-dir исходного проекта. Проверь отсутствие
   другого активного writer, чужих изменений, locks/prunable/missing paths.
2. Связанная существующая копия → reuse без reset/clean/stash/rebase/удаления.
   Неизвестные dirty tracked/untracked/ignored данные сохраняй; отдели собственные
   по фактам предыдущего выполнения, неоднозначность блокирует затронутую запись.
   Ранее пройденные проверки/review действительны только для тех же байтов/режимов.
   Найденная публикация/close — отдельный частичный эффект: по completion protocol
   проверь remote и выполни только отсутствующие действия, без повторной реализации.
3. Если связи ещё нет и нет признаков незавершённого создания, проверь исходный
   путь, HEAD/base, чистоту и native worktree config/setup scripts: создание может
   запускать проектный setup. Не выполняй неизвестные/неразрешённые side effects.
   Вызови `worktree_create` с именем, содержащим точный Beads ID. Используй
   **возвращённый** directory, не конструируй ожидаемый путь/branch. Проверь Git
   root/common-dir/branch/HEAD, tracked/untracked/ignored состояние и новый список.
   Если native стратегия дала не linked Git worktree — остановись, не подменяй
   проверку совпадением имени. Не создавай Epic-worktree.
   OpenCode 2.0.32 может вернуть новую копию с detached HEAD. Только для этой
   подтверждённо новой чистой копии проверь отсутствие ветки `mis/<exact-id>` и
   создай её обычным `git switch -c mis/<exact-id>` внутри возвращённого пути;
   затем отдельно проверь branch/HEAD/status. Это не fallback создания worktree.
   Коллизия ветки/неожиданно грязная копия → reconciliation, не reset/force.
   При resume не переключай существующую копию на новую ветку.
4. После успешной проверки bounded append/read-back в notes точного Bead:
   Task ID, абсолютный directory, реальная branch, base SHA. Это обычная связь
   результата в существующей записи, **не отдельный registry/handoff-файл**.
   При неизвестном эффекте create сначала inventory/Git/session reconciliation;
   orphan/несколько совпадений не разрешай повторным create. При потере этой связи
   остановись с путями-кандидатами, сохрани копию.
5. `session_move(directory=<verified path>)` выполняй **отдельным вызовом**.
   До move сохрани в контексте проверенный абсолютный installed root пакета и
   доступность нужных после перехода методов/resources (implement, sync-spec,
   review, publish, Beads completion/publication). Ignored `.opencode/` может
   отсутствовать в новой worktree. Если после move ID не обнаруживается, читай
   нужный `SKILL.md` и его условные ресурсы из **этой же проверенной установки**
   по сохранённому абсолютному пути, не угадывай новый root и не копируй/регистрируй
   пакет как часть Task. Недоступный обязательный метод — blocker зависимой части.
   После границы вызова отдельным действием проверь фактическую location сессии,
   `pwd`, `git rev-parse --show-toplevel`, `--git-common-dir`, branch и status.
   Не редактируй по предположению о мгновенном переключении. Если переход не
   применился/не совпал — blocker; не продолжай запись в старом root. После move
   перечитай применимые AGENTS/rules и проверь, что `bd where/context` указывает
   на тот же prepared workspace (возможен shared redirect; не init новую БД).

Подтверждённой non-Git/local-only работе не создавай фиктивную ветку, но установи
реальные пути/права/изоляцию и объясни исключение. Shared DB/services/порты не
становятся изолированными от наличия worktree. До запуска проверок примени
раздел «Изоляция ресурсов исполнения» `mis-proj-lib-common`: собственные
экземпляры, фактические адреса клиентов, раздельные изменяемые данные/артефакты
и освобождение только своих ресурсов, средствами стека потребителя.

## 3. Реализация и знания

Прочитай `references/verification.md` из установленного `mis-proj-lib-common`.
Установи проектные gate/affected/full acceptance и условия обязательной полной
приёмки; передавай политику, короткое основание выбора и привязанные к снимку
результаты между implement, review и publish. Не назначай повтор только из-за
смены этапа; после правок/интеграции переоцени применимость и затронутые проверки.

По политике делегирования common ограниченную реализацию поручай `standard`
(или выполняй в уже выбранном основном `standard`). Существенную нерешённую
архитектуру/дизайн, рискованные контракты и сложную диагностику сначала направь
`advanced` с ограниченным вопросом; при достаточном решении верни реализацию
standard. Проектирование не обязательно для каждой Task. Передай точную own
worktree и область; не редактируй её одновременно с исполнителем.

Загрузи `mis-port-op-implement-change`. Передай одну Task/Bug: принятые требования,
exclusions, актуальный код/base, точную разрешённую область, проектные constraints
и проверки, `implementation_mode: standard|tdd` **из правил потребителя** (если
ничто не требует TDD — standard). Не выдумывай design/spec prerequisite. В TDD
прочитай его собственный `references/tdd.md`, наблюдай ожидаемый RED, затем GREEN.
Эта операция не управляет Beads/worktree и не публикует.

Получив bounded результат, проверь реальные тесты и итоговый diff с новыми файлами,
режимами и удалениями. Затем загрузи `mis-proj-op-sync-spec`: передай ID, эту
проверенную worktree/кандидат, требования, checks и разрешённые docs. Получи spec
delta или обоснованный no-op; сохрани связь spec в Beads по execution protocol.
Документацию включи в тот же кандидат. Не объявляй локальный кандидат уже
интегрированным поведением основной ветки.

## 4. Независимое review и исправления

Загрузи `mis-port-op-review-change`, передай **отдельному reviewer-контексту `advanced`**
его методику, actual diff/base и полный воспроизводимый снимок (включая новые
файлы/spec/режимы), требования/rules и результаты checks. Этот flow явно требует
такой делегации; reviewer не автор/проектировщик/исправитель, работает read-only без tracker
writes, commit/push и сохранения отдельного review-файла. Для WIP зафиксируй
fingerprint путей/байтов/режимов с additions/deletions; не выдавай HEAD за WIP.
Область и исключения объяви до review; не скрывай относящиеся файлы.

Получи verdict/provenance/версию, required high/medium и optional low. Self-review
не gate. Недоступен профиль `advanced`, отдельный контекст или mandatory evidence →
`unverified`/blocker, не checked candidate. High/medium → исправление через
implement-change, повтор затронутых checks, sync-spec при изменении контракта и
независимый `advanced` re-review изменённого кандидата с прежними finding IDs. Low можно
обоснованно отложить. Ни число раундов, ни собственная правка не дают approval.
Любые последующие edits/integration инвалидируют review затронутой версии.

## 5. Публикация, завершение и recovery

Проверь фактические status/claim, dependencies, Git diff/status и соответствие
финального снимка tests/spec/review. Уточни по итоговой реализации сценарий
«как увидеть»: условия, каталог/ревизия, точка входа/команда, действия и ожидаемый
пользовательский либо технический эффект. Выполни доступную безопасную проверку;
непроверенный сценарий явно отдели от наблюдённого, назови причину. Автотесты не
заменяют пользовательскую демонстрацию, обязательный acceptance остаётся gate.
Не выполняй скрытый deploy или опасные действия ради демонстрации.
При новом blocker не называй результат
готовым к завершению. Сохрани в notes bounded краткий факт кандидата (worktree,
base/fingerprint, checks/review provenance, spec paths/no-op, остаток), без
копирования чужого review verdict от лица reviewer. В существующей записи
результата Task сохрани также краткий эффект и инструкцию «как увидеть», без
отдельного demo-файла/журнала. Unknown append сначала
read-back; не плодить одинаковые notes. Копия сохраняется, не удаляй её после push.

1. Загрузи `mis-proj-op-publish-change`. Передай полный кандидат и независимые
   checks/review, точную worktree/branch/base, разрешённую outgoing history,
   destination и источник direct-push authority. Интегрируй latest primary в own
   ветке; если tree изменился — затронутые проверки/spec и independent reassessment
   до push. Получи подтверждённые S/tree и fresh remote R, а не только exit 0.
   При конфликте/unknown сохрани commits/копию и точный blocker, Task не закрывай.
2. Прочитай [completion protocol](../mis-proj-op-beads/references/completion.md).
   Сохрани result в exact Task/Bug, закрой только после own acceptance/checks/review/
   Git remote, проверь parent Epic по **его** критериям и полным детям. Epic с
   недостигнутым результатом оставь открыт, это не отменяет успех отдельной Task.
3. Независимо опубликуй Beads/Dolt по его resource: exact required revision,
   authority на общую историю, fresh fetch/ancestry remote. Закрыт local, но push
   не подтверждён → частичный успех, не reopen/reclose. Если Git уже опубликован,
   не повторяй его ради Dolt. Recovery по explicit closed ID не создаёт worktree
   и не запускает implementation. При обоих подтверждённых каналах — read-only
   confirmation/no-op, не новый commit/push/append.

## 6. Один отчёт и остановка

✅ реальный полный либо частичный результат exact Task/Bug и состояние Epic,
что изменилось для пользователя (для технической работы — технический эффект,
честно указав отсутствие изменения пользовательского поведения, если так);
👀 как увидеть: условия, каталог/ревизия, команда/адрес, короткие действия и
ожидаемый результат; что реально проверено, что лишь инструкция и почему.
Для CLI/API/технической работы допустим наблюдаемый вывод вместо UI.
Отсутствие deploy/доступа укажи явно: push не равен доступности функции;
🧪 команды/результаты, independent review provenance точного snapshot, ограничения;
📚 spec paths/no-op; 🔗 ID, worktree/branch и отдельно Git remote/ref/S/tree/R,
Beads remote/branch/required revision/fresh R; ⚠️ точные неполные эффекты/blocker;
➡️ **одна** рекомендация `/mis-run <ID>` для recovery/определённой следующей
работы, в том числе с начальным интервью. Недостающий ответ внутри её scope сам
по себе не требует `/mis-plan`: если run ждёт ответа, следующий шаг — этот ответ.
`/mis-plan <цель или ID>` — когда надо выделить работу, изменить объём,
декомпозицию или граф, а не просто потому, что нет готовой к claim Task.
При реальном blocker рекомендуй его устранение/доступный prerequisite, не обход.
Рекомендацию следующего ID сверяй с fresh ready/ownership/blockers, но не claim и
не выполняй её. Не придумывай новый scope для открытия Epic. Остановись после
одного результата; отчёт/рекомендация не разрешают автоматический запуск очереди.
