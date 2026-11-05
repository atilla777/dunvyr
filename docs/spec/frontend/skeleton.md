# Frontend-скелет: toolchain, минимальная страница, dev-сервер, проверки

> Подтверждённое поведение, введённое Beads-задачей dunvyr-68c.2 (bootstrap-веха 1). Нормативные источники: [technology-and-infrastructure](../../rules/technology-and-infrastructure.md), [frontend](../../rules/frontend.md), [testing](../../rules/testing.md). Канонический fresh-clone flow — в корневом `README.md`.

## Toolchain и команды

- Версия Node — единственный источник истины: корневой `mise.toml` (`node = "24.22.2"`); `.nvmrc`/`engines` не используются (решение владельца 2026-11-05). Пакетный менеджер — npm в составе mise-Node.
- Все инструменты проверок (Vite, TypeScript, ESLint, Prettier, Vitest, Testing Library) — devDependencies `frontend/package.json`; точные версии — в `frontend/package-lock.json`. React/react-dom — единственные runtime-зависимости.
- Свежий клон: `mise install` → из `frontend/`: `npm ci` → проверки.
- Реальные команды проверок (из `frontend/`, все зелёные на снимке задачи):
  - `npm run lint` — ESLint 9 flat config (`typescript-eslint` recommended, `eslint-plugin-react-hooks`, `eslint-plugin-react-refresh`);
  - `npm run format:check` — Prettier 3 `--check` (lock/dist/coverage/node_modules исключены через `.prettierignore`);
  - `npm run typecheck` — `tsc --noEmit` (strict, `noUnusedLocals`/`noUnusedParameters`/`verbatimModuleSyntax`);
  - `npm run test` — `vitest run`;
  - `npm run build` — `tsc --noEmit && vite build` (production-сборка; `dist/` игнорируется Git).
- `make`-обёрток пока нет — это задача dunvyr-68c.3; состав будущего gate — в [testing](../../rules/testing.md).

## Минимальная страница

- Точка входа: `frontend/index.html` — `<div id="root">` + module-скрипт `/src/main.tsx`; `main.tsx` монтирует `App` в `StrictMode`, отсутствие `#root` — явная ошибка времени выполнения.
- `App` — заголовок `<h1>Dunvyr</h1>` и строка статуса скелета; роутинга, игровых компонентов и продуктовой стилевой темы нет. Стили — минимальный `index.css` (центрирование, типографика, светлая/тёмная схема через `prefers-color-scheme`).

## Dev-сервер и LAN

- `npm run dev` поднимает Vite dev-сервер на `localhost` по умолчанию.
- LAN-биндинг — явный opt-in: переменная окружения `DUNVYR_DEV_HOST` (LAN-IP или `0.0.0.0`) в `vite.config.ts` задаёт `server.host`; по умолчанию не `0.0.0.0` (правило LAN: открытие listener — только после осознанной настройки firewall и allowed origins). Итоговый LAN-запуск одной командой — задача dunvyr-68c.3.
- Проверено на снимке задачи: dev-сервер отдаёт `GET /` → 200 (HTML с root-контейнером и module-скриптом) и `GET /src/main.tsx` → 200 (Vite-трансформированный модуль с React-mount).

## Тестовая архитектура

- Component-тест `src/App.test.tsx` реально рендерит `App` через `@testing-library/react` в jsdom и проверяет заголовок уровня 1 «Dunvyr» и строку статуса; матчеры — `@testing-library/jest-dom/vitest` (setup `src/test/setup.ts`).
- Конфигурация Vitest — в `vite.config.ts` (`environment: 'jsdom'`, `css: false` — стили в тестах не импортируются).

## Ограничения (ещё не существует)

`Makefile`/`make`-цели и git hooks (dunvyr-68c.3), Playwright/E2E (dunvyr-68c.4), CI (dunvyr-68c.5). Игровые UI-компоненты, WebSocket, роутинг, продуктовая стилевая тема — будущие вехи. Автоматизированная браузерная проверка страницы появится с задачей E2E; открытие страницы в реальном браузере — ручной шаг из README.
