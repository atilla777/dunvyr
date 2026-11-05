# Инженерные правила Dunvyr

Эти документы описывают **как** реализовать требования из `docs/product/`. Проектный контракт выше общих пожеланий агента; совместимость с MIS оговорена явно.

- [Границы и владение Bounded Contexts](bounded-contexts.md)
- [Clean Architecture, зависимости, событийные реакции](architecture.md)
- [DDD, контракты и инварианты](domain-design.md)
- [FastAPI, SQLAlchemy и данные](backend-and-data.md)
- [React, real-time и адаптивность](frontend.md)
- [LLM и контролируемые команды](ai-integration.md)
- [TDD, unit/integration/E2E и gates](testing.md)
- [MIS, Git, CI и публикация в main](development-workflow.md)
- [Стек, окружение и запуск в LAN](technology-and-infrastructure.md)
- [Приватность, безопасность и секреты](security-and-privacy.md)
- [Правила работы с документацией и задачами](knowledge-and-sdlc.md)

**При первом bootstrap** обязательно создать реальные инструменты тестирования и выполнить compatibility gate процесса `mis-run` → публикация в `main` (см. `development-workflow.md`); одно наличие этих Markdown-файлов не означает готовность к запуску разработческих скиллов.
