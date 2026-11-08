---
type: Architecture Decision
title: Атомарная встреча кампании и событие communication
status: accepted
---
# GameSession: одна транзакция, отдельная доставка

## Контекст

`campaigns` владеет встречами, правами организатора и revision кампании.
Клиент восстанавливает встречу через REST snapshot и общий поток `communication`.
Сохранение встречи без durable события либо receipt нарушает retry/reconnect.
Существующий postcommit publisher `member_joined` этого требования не обеспечивает;
его контракт и поведение не меняются.

## Решение

Application use case `campaigns` координирует одну короткую транзакцию:
состояние/история встречи, точный receipt команды и событие `game_session_changed`.
Composition root инъецирует одну SQLAlchemy Session двум owning adapters.
Публичные immutable `GameSessionState`/`GameSessionChanged` и Protocol
`GameSessionEventStager` не раскрывают ORM или Session. Communication staging
пишет **только свои таблицы**, не создаёт сессий, не commit/rollback и не доставляет.
Только campaigns UoW завершает транзакцию; ошибка на любой стадии откатывает всё.
Это конкретный transaction participant, не универсальный bus/outbox framework.

SQLite write-lock получается первым UPDATE per-campaign state перед чтением
receipt и состояния. Дополнительно запись защищена revision CAS и partial UNIQUE
по активным running/paused встречам. Исторические ended строки сохраняются.
Revision монотонна между встречами; миграция backfill и создание кампании дают 0.
Авторизация проверяется до replay; ключ уникален в (campaign, actor, key), payload
включает action, target session и expected_revision. Replay возвращает исходный
снимок, а не текущее состояние. Изменённый payload конфликтует до stale-check.
Один joined SELECT читает revision вместе с состоянием встречи без torn read.

После commit отдельный notifier перечитывает committed event и уведомляет hub.
Ошибка доставки не меняет успех команды. Snapshot истории всегда включает полное
`game_session_state`, даже если нужное событие старше последних 200 записей либо
курсор вернул пустой список. Клиенты применяют state по монотонной revision;
sequence остаётся общим курсором chat/reconnect. Состояние/персонажи/приключение
при end и следующем start не сбрасываются.

## Последствия и проверки

Нет межконтекстных импортов внутренних модулей и чужих SQL-записей. Общая
транзакция предполагает принятую единую SQLite и composition root монолита.
SQLite сериализует writers всей БД; транзакция не содержит сети/LLM.
Integration tests проверяют отдельные файловые соединения (start/start,
pause/end, одинаковый ключ), torn read, rollback staging/receipt/commit,
postcommit recovery, restart/replay, migration/backfill и сохранность данных.
