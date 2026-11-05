# Dunvyr

Dunvyr — локальная многопользовательская веб-платформа для совместных настольных RPG с AI Dungeon Master. Первый вертикальный продукт: короткое законченное киберпанк-приключение на 1–2 встречи; правила универсальны для разных сеттингов.

**Это документационный репозиторий, а не работающий код приложения.** Приложение, `Makefile` и CI ещё не созданы; их создаст первая bootstrap-задача через `/mis-plan` → `/mis-run`.

## Где читать

- [Точка входа AI-агента](AGENTS.md)
- [OKF Bundle](docs/index.md)
- [Требования](docs/product/index.md)
- [Правила](docs/rules/index.md)
- [Что уже решено и что открыто](docs/product/decisions-and-open-questions.md)

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
