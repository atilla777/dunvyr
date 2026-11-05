---
okf_version: "0.2"
---
# Dunvyr — OKF Bundle

Главная точка входа в продуктовые требования и инженерные правила. Это **не** спецификация реализованного приложения.

## Продукт (`docs/product/`)

- [Указатель требований](product/index.md)
- [Видение, границы MVP](product/vision.md)
- [Игровой процесс и ходы](product/gameplay.md)
- [Сценарии, сцены и испытания](product/adventures-and-encounters.md)
- [Dunvyr Rules и бои](product/rules-system.md)
- [Персонажи и развитие](product/characters.md)
- [AI Dungeon Master и NPC](product/ai-dungeon-master.md)
- [Общение, важные события и журнал](product/communication-and-journal.md)
- [Многопользовательская игра и доступ](product/multiplayer-and-access.md)
- [Интерфейс и доступность](product/user-experience.md)
- [Критерии приёмки MVP](product/mvp-acceptance.md)
- [Ориентиры вех MVP (не Beads-задачи)](product/mvp-delivery-outcomes.md)
- [Принято / открыто / отложено](product/decisions-and-open-questions.md)

## Правила (`docs/rules/`)

- [Указатель инженерных правил](rules/index.md)
- [Bounded Contexts и их владение](rules/bounded-contexts.md)
- [Слои, зависимости, взаимодействия](rules/architecture.md)
- [DDD и контракты](rules/domain-design.md)
- [Бэкенд и данные](rules/backend-and-data.md)
- [Frontend и адаптивность](rules/frontend.md)
- [Интеграция LLM](rules/ai-integration.md)
- [Тесты и gates](rules/testing.md)
- [Git/CI и MIS](rules/development-workflow.md)
- [Технологии и локальная инфраструктура](rules/technology-and-infrastructure.md)
- [Безопасность и приватность](rules/security-and-privacy.md)
- [SDLC и управление знаниями](rules/knowledge-and-sdlc.md)

## По мере реализации

- [Спецификации реализованного поведения](spec/index.md)

Корневой [AGENTS.md](../AGENTS.md) — маршрутизатор агента. `docs/product/` — авторские продуктовые намерения, `docs/rules/` — обязательные инженерные ограничения, Beads — план и критерии задач, `docs/spec/` — подтверждённые контрактные детали реализованного поведения.
