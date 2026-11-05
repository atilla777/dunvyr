---
type: Engineering Rule
title: Стек, окружение и локальная эксплуатация
status: accepted
---
# Технологии и запуск MVP

## Выбранный стек

- Backend: Python + FastAPI, SQLAlchemy 2.x, Alembic, SQLite.
- Frontend: React + TypeScript + Vite, адаптивный UI, SVG/DOM для сцен и карты MVP.
- Realtime: WebSocket, один локальный серверный процесс.
- AI: внешний конфигурируемый LLM-provider через серверный port/adapter.
- TTS: браузерное озвучивание по кнопке, fallback без аудио.
- Tests: pytest/Ruff/type checking/Import Linter, Vitest/Testing Library, Playwright, GitHub Actions.
- VCS/SDLC: Git monorepo (один MIS-проект), OpenCode + MIS + Beads/Dolt.

Без Redis, брокера сообщений, выделенного worker pool, Postgres, Kubernetes, облачных сервисов хранения и необходимости платного хостинга в MVP. При появлении доказанной нагрузки пересмотреть через отдельное решение.

## Структура проекта

```text
dunvyr/
  AGENTS.md
  README.md
  docs/{product,rules,spec}/
  backend/src/dunvyr/{identity,campaigns,characters,adventures,gameplay,communication,narration,shared}/
  frontend/
  adventures/                 # prepared scenario assets (после реализации)
  .opencode/                  # устанавливается MIS, не заполнять вручную
  .beads/                     # подготавливает явный /mis-install
```

Элементы кроме `AGENTS.md`, `README.md`, `docs` **отсутствуют в документационном наборе** и создаются через задачи.

## LAN запуск

Один компьютер запускает FastAPI/React по локальному IP и порту, другие браузеры в той же доверенной Wi-Fi сети подключаются по адресу/приглашению. Для локального MVP допускается HTTP в LAN с осознанными ограничениями; **для выхода в интернет HTTPS обязателен**. Сервисы dev/production конфигурируются отдельно. Нельзя опираться на `localhost` с телефонов. Открытие listener `0.0.0.0` — только после осознанного настройки firewall и allowed origins.

Для developer experience — один документированный запуск одной командой после bootstrap (например, `make dev`, точная реализация определяется при создании проекта). Основная ветка и GitHub remote существуют до MIS install; worktree path `.sdlc/worktrees`, отдельно от приложения. Создание embedded Beads только через `/mis-install`, без самовольного `bd init` в разных worktrees.

## Сохранность данных

SQLite БД — локальный персистентный файл вне Git. Сценарии и assets — версионируемые файлы. Переносить запускаемые компоненты без миграции нельзя; обновления схемы — Alembic. Backup/restore документируется и проверяется. Ключ AI только в env/secret store, не в source/коммите и не в frontend.

## Development / CI

GitHub Actions проверяет Linux environment и browser smoke; сервисы и тестовая база запускаются изолированно. CI не требует подключения реального AI. Проверенные версии Python/Node/tooling фиксировать в файлах проекта при bootstrap; здесь не угадывать номера версий.
