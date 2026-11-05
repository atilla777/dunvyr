# Dunvyr

Dunvyr — локальная многопользовательская веб-платформа для совместных настольных RPG с AI Dungeon Master. Первый вертикальный продукт: короткое законченное киберпанк-приключение на 1–2 встречи; правила универсальны для разных сеттингов.

**Backend-скелет приложения уже создан** в `backend/`: FastAPI app-factory с health-эндпоинтом, SQLAlchemy 2.x + Alembic, pytest, Ruff, mypy и Import Linter. Frontend, `Makefile` и CI ещё не созданы — это следующие bootstrap-задачи.

## Где читать

- [Точка входа AI-агента](AGENTS.md)
- [OKF Bundle](docs/index.md)
- [Требования](docs/product/index.md)
- [Правила](docs/rules/index.md)
- [Что уже решено и что открыто](docs/product/decisions-and-open-questions.md)

## Backend

Версия Python и `uv` зафиксированы в корневом `mise.toml`; Ruff, mypy, pytest и Import Linter — dev-зависимости проекта из `backend/pyproject.toml`, точные версии — в `backend/uv.lock`.

С чистого клона:

```bash
mise install                      # ставит Python 3.14.10 и uv из mise.toml
cd backend
mise exec -- uv sync              # создаёт backend/.venv из uv.lock
mise exec -- uv run ruff check .
mise exec -- uv run ruff format --check .
mise exec -- uv run mypy
mise exec -- uv run pytest -m unit
mise exec -- uv run pytest -m integration
mise exec -- uv run pytest
mise exec -- uv run lint-imports
```

Если mise активирован в shell (`mise activate`), префикс `mise exec --` не нужен: достаточно `uv sync` и `uv run ...` из `backend/`. Проверить версию Python: `mise exec -- python --version` → `Python 3.14.10`.

Integration-тесты применяют настоящий Alembic pipeline к SQLite в памяти (`sqlite+pysqlite:///:memory:`); файл рабочей БД при тестах не создаётся. Миграции вручную: `mise exec -- uv run alembic upgrade head` (URL — из `DUNVYR_DATABASE_URL`, по умолчанию `sqlite:///./dunvyr.db`).

## Среда агентной разработки (установлена)

- **MIS** установлен из проверенного upstream https://github.com/atilla777/mis; точная ревизия зафиксирована в `.opencode/mis-installation` — проверяй этот файл, а не этот README.
- **OpenCode 2.x** с native worktree (`.sdlc/worktrees`) и профилями агентов `standard`/`advanced`.
- **Beads `bd`** с embedded Dolt; история трекера публикуется в `refs/dolt/data` этого же Git remote.
- Доступные операции: `/mis-install`, `/mis-plan`, `/mis-run`, `/mis-bug`, `/mis-status`, `/mis-update`.

Обновление MIS — только явно через `/mis-update` по актуальной процедуре upstream README; самовольные изменения установленного пакета запрещены.

## Публикация изменений

Интеграция в `main` — **прямая публикация по протоколу MIS** (`mis-proj-op-publish-change`): полный обязательный gate локально на интегрированном снимке до push, независимый read-only AI-review, non-force push с read-back, CI GitHub Actions на push пост-фактум (решение владельца 2026-11-05). Закрытая Task означает подтверждённую публикацию, а не продуктовую приёмку. Детали — в [development-workflow](docs/rules/development-workflow.md).

## Что дальше

1. `/mis-plan` — план первой вехи: технический bootstrap (скелет FastAPI + React, реальные `make`-команды из [testing.md](docs/rules/testing.md), CI на push в `main`, git hooks, доступный по LAN запуск).
2. `/mis-run` — реализация задач вехи с проверками, независимым review и публикацией по протоколу.

Документация различает подтверждённые продуктовые решения, предложения для реализации и открытые параметры; открытые параметры не принимать молча.
