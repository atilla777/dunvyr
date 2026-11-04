---
name: mis-proj-op-install
description: Install MIS and explicitly prepare or restore a consumer's embedded Beads workspace with Dolt history in the project's Git remote. Use for /mis-install or first setup, never implicit initialization during plan/run/update.
---

# Установить MIS и подготовить Beads

Явная установка в существующий Git-проект, не создание приложения и не Task.
Не устанавливай системные зависимости, не выбирай стек/правила приложения,
не создавай задачи и не запускай plan/run. Обновление пакета без подготовки
Beads — `mis-proj-op-update`. Оба режима используют один package script.

До вопросов, обсуждения решений или сообщения о проблеме загрузи
`mis-proj-lib-common` и прочитай его `references/dialogue.md`. При первой установке,
когда пакет ещё не обнаруживается, прочитай библиотеку и ресурс по абсолютным
путям из той же проверенной внешней копии MIS, что и этот скилл. Не ожидай
этапа review: общие правила диалога действуют с начала операции.

## 1. Preflight до записи

- Прочитай AGENTS.md (если есть), status/log/remotes и применимые правила
  публикации. Сам MIS не является потребителем. Сохрани чужие файлы, hooks,
  инструкции и существующие БД; не выполняй reinit/force/reset/delete/migration.
- Нужны Git, Python 3, OpenCode с native worktree/session tools, bd и Dolt.
  Проверенный baseline: OpenCode 2.0.32, bd 1.3.1, Dolt 2.4.1; прочитай реальные
  help init/bootstrap/remote/config. Нет средства — точный blocker, не auto-install.
- Установи точный root, primary branch и единственный разрешённый Git destination.
  Для существующего проекта соблюдай его dedicated worktree/review правила;
  worktree создавай/находи native OpenCode, переходи session_move с read-back.
  Новую БД подготавливай в canonical root проекта, не отдельную для каждой
  linked worktree. Если правила запрещают запись туда, останови этот этап и
  укажи конфликт; не создавай альтернативную БД ради обхода.
- Проверь origin доверенного внешнего checkout `https://github.com/atilla777/mis`,
  fetch и зафиксируй полный target SHA. До запуска скрипта проверь его источник.
  Подтверди достижимость target из свежего доверенного upstream ref (без аргумента
  это origin/main); наличие только локального Git-объекта не подтверждает публикацию.
- Проверь local `.beads/`, bd where/context/status, ambient BD_/BEADS_ overrides,
  tracked config/metadata и фактический Dolt remote. Ошибка открытия/неполная
  копия/чужой redirect не равны отсутствию. Existing database → только проверка
  и reuse; иной mode/destination/history не перенастраивай автоматически.
- Без БД сначала проверь удалённую историю **проекта-потребителя**: из его root
  выполни `git ls-remote <consumer-project-origin-URL> refs/dolt/data`, используя
  destination проекта из первого preflight, не origin внешнего checkout MIS.
  Origin MIS служит только источником пакета и никогда не является Beads remote.
  Сбой/отказ доступа — unknown и blocker, не пустой remote.
  Безусловный новый init при существующем ref запрещён. Старые JSONL/backups,
  конфликтующая `.beads/` или другое хранилище требуют отдельного решения.

## 2. Пакет — общий engine с update

Через проверенный внешний checkout (до обнаружения skill в потребителе):

```sh
python3 /external/mis/scripts/install.py /consumer --revision FULL_TARGET_SHA
```

Это read-only preflight; для применения тот же вызов с `--apply`.
Копируются только package Git blobs и `.opencode/mis-installation`; рабочие
правки источника не устанавливаются. Полный preflight защищает local edits,
unknown resources, symlinks/hard links. Повтор того же SHA — no-op;
установленная другая ревизия → `/mis-update`, не обход через install.
Скрипт **не** делает bd init, fetch, commit/push, AGENTS/config или установку ПО.
При частичном успехе сохраняй факты; повторяй только недостающее, без rollback
чужих файлов. Не запускай одновременно с другим writer.

## 3. Embedded Beads и тот же репозиторий

Только при явной установке и после разрешённого preflight:

1. Если БД уже исправна — проверь embedded, принадлежность проекту, prefix,
   native types и remotes, сохрани их. Для подходящего workspace init не нужен.
2. Если local БД нет, а remote `refs/dolt/data` есть: `bd bootstrap --dry-run
   --json` должен предлагать clone **проверенного Git remote проекта-потребителя**,
   не origin MIS, backup/JSONL/fresh.
   После проверки плана `bd --sandbox bootstrap --non-interactive`; затем
   read-back существующих ID/history и отсутствие конкурирующей новой БД.
   Несовместимость формата/capabilities блокирует, не fallback на fresh init.
3. Если local БД и remote ref доказанно отсутствуют: выбери стабильный issue
   prefix по проекту; `bd --sandbox init --prefix <prefix> --non-interactive
   --skip-agents --skip-hooks`. По умолчанию embedded; ambient server overrides
   не должны подменять режим. Проверь actual context/status, а не только exit 0.
   Init может создавать Git-коммиты/служебные файлы: заранее проверь актуальное
   поведение в disposable fixture. Перед init canonical index/worktree должны
   быть чистыми: собственный пакет можно сохранить отдельным локальным коммитом
   в разрешённой области, без push до итоговых проверок/review. Чужой index/WIP
   не stage/commit/reset и не обходи новой пустой БД в linked worktree.
4. Для **нового** workspace настрой Dolt `origin` на тот же проектный Git remote:
   например `git@github.com:owner/project.git` →
   `git+ssh://git@github.com/owner/project.git` (HTTPS → `git+https://…`).
   Локальные git fixtures используют `git+file:///absolute/bare.git`.
   Сравни identity репозитория, не только строки. Не угадывай unsupported URL.
   URL с паролем/token не сохраняй и не выводи; используй SSH/credential helper.
   Используй `bd --sandbox dolt remote add origin <git+URL> --allow-git-origin`
   и `bd --sandbox config set sync.remote <git+URL>`, затем config/remote/context
   read-back. Существующий несовпадающий remote — blocker, не silent replace.
5. История Dolt хранится в `refs/dolt/data` того же Git-репозитория, не в
   `refs/heads/main` и не коммитом живого `.dolt`/локальной БД. В Git идут только
   проверенные project config/metadata/ignore и пакет; исключи локальные БД,
   credentials, locks и caches. Проверь общий workspace routing из linked
   worktree: он должен вести к той же canonical БД, а не init второй.

## 4. Проверить, опубликовать, остановиться

После подготовки доступны AGENTS.md и `docs/product/`, `docs/spec/`, `docs/rules/`
с настоящими командами проверок и стратегией разработки. Их отсутствие — явно
неготовый проект: не выдумывай продукт/стек/TDD. С разрешения добавь лишь короткую
MIS-маршрутизацию/ссылки к существующим инструкциям, не переписывай авторские правила.
Перед выбором проверок прочитай `references/verification.md` из той же common:
проект определяет быстрый gate, затронутые проверки и полную приёмку. Не вводи
полный regression на каждый push и не сокращай существующий gate при неясной
политике. Если помогаешь подготовить инструкции, согласуй политику с владельцем;
пакетный скрипт её не генерирует, существующим проектам она не навязывается.
Убедись, что пакет versioned и доступен новым worktree/сессиям; не force-add
ignored файлы и не коммить всю `.opencode/` без проверки.

Проверь точные skill IDs/paths/bodies и command templates в реальном OpenCode,
package no-op, bd context/status, существующие ID и remote history. Применимые
проектные проверки/review до Git-публикации обязательны. Для требуемого review
загрузи `mis-proj-lib-common` и его `references/delegation.md`: только отдельный
read-only контекст `advanced`, не автор/проектировщик/исправитель. Недоступен
профиль/контекст — `unverified`/blocker без замены на general/self-review;
re-review следует той же политике. Git и Dolt — отдельные
эффекты даже при одном GitHub repository. Для Dolt загрузи `mis-proj-op-beads`
и его `references/dolt-publication.md`: authority на shared history,
non-force push и fresh remote confirmation; приоритет не обходит ограничения.
При неизвестном push сначала confirmation, не повтор init/bootstrap.

Отчёт: ✅ пакет/готовность проекта/Beads отдельно; 👀 точная команда проверки
и ожидаемый эффект; 🧪 что реально проверено; 🔗 source SHA, Git remote/SHA,
Beads mode/path/prefix/remote/required revision и подтверждение публикации;
⚠️ неполнота/блокер; ➡️ одно действие (новая сессия и `/mis-plan <цель>` только
если проект готов). Не запускай планирование или следующую Task автоматически.
