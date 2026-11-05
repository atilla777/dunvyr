---
type: Testing Policy
title: Тестовые уровни, TDD, git hooks и CI
status: accepted
---
# Стратегия тестирования Dunvyr

## Принцип

**TDD для новых/изменяемых доменных инвариантов** (`characters`, `gameplay`, `adventures`, права и событийная согласованность). Для infrastructure/API/React — обязательные подходящие проверки, но тест не обязан предшествовать каждой строке UI-кода.

Не делать полный end-to-end прогон на каждый edit, commit или push. MIS требует три разных вида доказательств: быстрый обязательный gate, затронутые проверки и полная приёмка при нужном риске/релизе. Не отключать защиту ради ускорения и не объявлять незапущенный набор «успешным».

## Уровни

| Событие | Проверки | Правило |
| --- | --- | --- |
| Внутри Task | Затронутые unit/contract/integration/UI + потребители изменённого публичного API | Обязательно, из реального scope |
| Pre-commit | Быстрый lint/format/static check изменённых файлов | Должен быть быстрым; без E2E |
| Pre-push | Быстрые unit и архитектурные import contracts | Обязательно; без браузеров |
| Публикация в `main` — до push (локально, интегрированный снимок) | Все unit, интеграционные, architecture, frontend tests, **E2E smoke** desktop+mobile | Обязательный gate до push |
| `main` после push (GitHub Actions) | Полный CI-набор | Пост-фактум подтверждение и аудит |
| Приёмка MVP / высокая неопределённость/риск | Расширенные E2E, сценарные варианты, полная регрессия | Обязательно по фактическому риску |

Изначально при малом числе E2E smoke/full могут совпадать; не создавать сложное разделение раньше необходимости. При росте нагрузки smoke остаётся в gate публикации, full — вручную/по milestone/при необходимости по расписанию.

## Инструменты и цели команд

Python: pytest, pytest-cov, Ruff, mypy, Import Linter. React: Vitest + Testing Library, ESLint/Prettier, TypeScript typecheck. E2E: Playwright (настоящие браузеры, real-time, mobile viewport), внешний AI только через fake adapter в CI — ещё не реализован.

Публичный интерфейс — корневой `Makefile`. Он запускает команды через `mise exec -- ...`, поэтому работает и без `mise activate`; GNU make, Linux.

| Цель | Состав |
| --- | --- |
| `make setup` | `mise install`; в `backend/` — `uv sync`; в `frontend/` — `npm ci`. |
| `make lint` | backend: `ruff check .`, `ruff format --check .`, `mypy`; frontend: `npm run lint`, `npm run format:check`, `npm run typecheck`. |
| `make test-unit` | backend: `pytest -m unit`, `lint-imports`; frontend: `npm run test` (Vitest run). |
| `make test-integration` | backend: `pytest -m integration`. |
| `make test-affected SCOPE=<backend\|frontend\|all> ARGS='<селекторы>'` | нативные селекторы тестов; см. ниже. |
| `make dev` | backend + frontend одной командой, LAN-listener по умолчанию. |
| `make hooks` | установка git hooks копированием из `scripts/hooks/`. |

`make test-affected` не вводит `--changed` и не реализует собственный dynamic selector; он честно передаёт нативные аргументы:

- `SCOPE=backend` → из `backend/`: `uv run pytest <ARGS>` — пути, `-k`, `-m`;
- `SCOPE=frontend` → из `frontend/`: `npm run test -- <ARGS>` — паттерны файлов Vitest;
- `SCOPE=all` (по умолчанию) → те же `<ARGS>` последовательно в обоих стеках.

Пустой `ARGS` или неизвестный `SCOPE` — usage-ошибка с ненулевым exit. `ARGS` со сложным shell-quoting передавать в одинарных кавычках.

Изоляция: backend unit/integration выполняются в процессе pytest на SQLite в памяти (`sqlite+pysqlite:///:memory:`, per-process) с настоящим Alembic pipeline для integration; `TestClient` работает без сетевых портов; файл рабочей БД не создаётся. Frontend — jsdom/Vitest без браузера. На тест-целях `RUN=<id>` задаёт отдельный pytest cache (`-o cache_dir=.pytest_cache/run-<id>` внутри игнорируемого `.pytest_cache/`), чтобы параллельные прогоны не конфликтовали по артефактам; frontend-прогоны общих тестовых артефактов не пишут.

Git hooks устанавливаются `make hooks` в `$(git rev-parse --git-path hooks)` копированием (не symlink):

- `pre-commit` — только staged-файлы (`.py` в `backend/`: `ruff check` + `ruff format --check`; `.ts/.tsx/.js/.jsx` в `frontend/`: `eslint` + `prettier --check`); без E2E, без релевантных файлов — быстрый exit 0;
- `pre-push` — backend `pytest -m unit` + `lint-imports`, frontend `npm run test`; без браузеров.

`make test-e2e-smoke`, `make test-e2e-full` и `make test-ci` **ещё не существуют** — их создаёт задача 68c.4. CI-файл GitHub Actions создаёт задача 68c.5. До этого полный gate публикации с E2E smoke desktop+mobile не обеспечен Makefile, и это нельзя заявлять как выполненное.

## Риски, требующие дополнительных проверок

- Изменение публичного контракта context: все потребители и контрактные сценарии.
- Изменение правил damage/XP/turns: таблицы граничных случаев, property-based проверки, replay с фиксированными бросками.
- Изменение persistence/transaction/reconnect: интеграция, конкурентные команды, миграции, идемпотентность.
- Изменение gameplay UI/голосования/mobile: Playwright smoke соответствующего сценария.
- Изменение карты/сценария: валидация графа, отсутствие утечки скрытых данных, Fail Forward и достижимость финалов.

## Доказательства и повторные проверки

Агент указывает фактически запущенные проверки, результаты и ограничения. Не повторять без оснований тесты неизменённого снимка; после изменений исходников/CI/hook — переоценить затронутый scope. Скриншоты/артефакты визуальных изменений полезны, но не заменяют автоматические проверки. CI GitHub Actions на push в `main` должен быть устойчивым и воспроизводимым без секретов реальных LLM.
