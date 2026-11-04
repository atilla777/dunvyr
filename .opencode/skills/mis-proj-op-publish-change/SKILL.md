---
name: mis-proj-op-publish-change
description: >-
  Integrate one checked MIS change in its existing dedicated worktree into the
  established primary remote Git branch, recheck the complete integrated snapshot
  and independently verify non-force publication. Not Beads completion, Dolt push,
  worktree preparation, source-checkout maintenance, release or deployment.
---

# Публикация одного Git-result

Caller передаёт точный Task/Bug, требования/границы, authority на direct push,
проверенную own worktree/branch/common-dir/base, candidate и checks/spec/review.
Примени `mis-proj-lib-common`; через `mis-proj-op-beads` свежо проверь identity,
ownership, directed blockers и parent constraints перед зависимой публикацией.
Не создавай worktree, не переключай ветки и не записывай tracker. PR-only policy,
неизвестный destination/права, потеря ownership или blocker останавливают push.
Полное поручение flow может покрывать обычный direct push, но не чужие commits,
force, новый remote/ref или bypass правил. Не требуй нового согласования, если
действующие полномочия уже установлены. Не переносить policy разработчиков MIS
в потребителя. Нет Feature/design/RID gates или Fast review exception.

До интеграции прочитай `references/verification.md` из установленного
`mis-proj-lib-common`: нужен проектный gate и обоснованный дополнительный набор,
не безусловный полный regression перед каждым push. Сохрани более строгую
политику; неизвестная политика не разрешает сокращать существующий gate.
Используй применимые результаты implement/review без процедурного повтора,
но не обходи hooks/CI и не переноси evidence на иной снимок без обоснования.

## Входной снимок и область

1. Установи primary remote/ref из фактов проекта, не из literal `main`. Прочитай
   remotes/URLs, upstream, HEAD, status (tracked/untracked/ignored), index, diff и
   историю. Неподходящий upstream не исправляй настройкой: explicit destination
   допустим только если установлен независимо; неоднозначность — blocker.
2. Для записи нужна существующая dedicated own linked worktree точного Task,
   отдельно от source checkout, с единственным writer. Не reset/clean/stash/rebase,
   не меняй local primary, не включай чужие файлы/секреты/Beads storage/кэши.
   Неизвестное dirty состояние сохраняй; конфликт с собственным результатом
   блокирует затронутую запись. Stage только разрешённые пути, не `git add .`.
3. Нужны requirements/checks и независимый review **полного публикационного
   снимка**: base + overlays, новые/удалённые файлы, modes, неизменённые base files,
   заранее объявленные exclusions. Reviewer не автор/исправитель, provenance и
   версия проверяемы, high/medium отсутствуют, low имеют disposition. HEAD не
   описывает WIP. Fingerprint только diff не доказывает полный tree. YAML/report
   file не обязателен. Missing/failed/unknown review не approval.
4. Проверь **всю исходящую историю** относительно свежего target: каждый commit,
   path/content/mode и merge ancestry, не только Task diff или последний commit.
   Unreviewed посторонняя история блокирует push даже при проверенном tip.

## Commit → merge → recheck → push → read-back

1. `git fetch --quiet <remote>`; проверь точный fetched primary ref и свежий
   `git ls-remote <remote> <primary-ref>`. Ошибки/изменение refs — reconciliation,
   не пустая ветка. Сначала восстанови прежний sent SHA **S** из Beads/истории
   сессии, если это retry. Fresh fetch + `git merge-base --is-ancestor <S> <R>`
   exit 0 подтверждает прежний result: no-op push, даже при более новом/dirty
   local state. Exit 1 — absent, прочие ошибки — unknown. Не подменяй S новым HEAD.
   Подтверди точный tree S и применимость checks/review; не объявляй более поздние
   неизвестные изменения проверенными. No-change read-back не требует новой копии.
2. Если остались intended изменения, проверь staged diff, commit только свою область
   в уже выбранной ветке. Сопоставь committed tree с полным reviewed snapshot.
   Hook edits/изменение modes также инвалидируют затронутые checks/review.
   Без изменений/unsent commits не делай пустой commit или лишний push.
3. Интегрируй fetched primary **в own ветку** обычным `git merge <remote-primary>`
   по политике проекта. Не используй shared local primary как integration copy.
   Обычный разрешимый конфликт исправь в своей области; существенный конфликт
   требований/чужих данных сохрани и верни `conflict`. Не маскируй ошибку merge,
   не выполняй разрушительный abort/reset. Не push при незавершённом merge.
4. Зафиксируй resulting SHA/tree и входные версии. При любом изменении полного
   tree (даже clean merge/совместимый upstream) переоцени затронутые проверки с
   зависимыми сценариями, выполни инвалидированные и обеспечь применимое
   подтверждение обязательного проектного gate. Перепроверь
   contracts/spec и получи независимую reassessment нового **целого** снимка;
   reviewer может переиспользовать доказательства неизменённых частей. Если tree
   побайтово/mode идентичен, явно обоснуй сохранность checks/review. Не выдумывай
   exclusions после review. Spec описывает результат после интеграции, не ложный
   статус «уже опубликовано»; нужная doc correction проходит те же gates.
5. Непосредственно перед push снова проверь Task/ownership/blockers, primary
   destination, outgoing commits/paths/tree, checks/review и чистоту собственной
   области. Сохрани exact S/tree в результате сессии **до** сетевой попытки.
   `git push --quiet <remote> <S>:<primary-ref>` — explicit non-force refspec,
   без hook bypass. Запрещены force, deletion и push всех веток.
6. Независимо от exit/timeout push сделай fresh `ls-remote` и fetch выбранного
   remote/ref. Проверь согласованность наблюдаемого R (при гонке перечитай),
   reachability S из R и `S^{tree}` против checked snapshot. Exit 0 не receipt.
   Remote advancement/rejection → сначала confirmation S, затем, если доказанно
   отсутствует, свежая интеграция/recheck/review в той же копии и только недостающий
   push. Unknown не успех и не разрешение слепого replay/recommit.

Верни `ok|blocked|conflict|error`, ID, authority source, directory/branch/base,
remote URL/ref, полный outgoing scope, S/tree, fresh R/ancestry, checks/reviewer
provenance/applicability, push attempted/confirmed/no-op, сохранённые эффекты и
остаток. `ok` только с independent remote evidence. Не обновляй source checkout
по умолчанию, не close Task/Epic, не push Dolt, не deploy и не выбирай новую Task.
