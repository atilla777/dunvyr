# Dunvyr — единый публичный интерфейс локальных команд.
#
# Требуются GNU make, Linux и mise в PATH. Все команды выполняются через
# `mise exec -- ...`, поэтому `mise activate` не обязателен.
#
# `RUN=<id>` на тест-целях включает отдельный каталог pytest cache
# (`.pytest_cache/run-<id>`), чтобы параллельные прогоны не делили артефакты.

SHELL := bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

MISE := mise exec --
BACKEND := backend
FRONTEND := frontend

RUN ?=
PYTEST_CACHE_ARGS = $(if $(strip $(RUN)),-o cache_dir=.pytest_cache/run-$(strip $(RUN)))
SCOPE ?= all
ARGS ?=
HOOKS_DIR := $(shell git rev-parse --git-path hooks)

.PHONY: help setup lint test-unit test-integration test-affected dev hooks

help:
	@printf '%s\n' \
		'Dunvyr — локальные команды (запускать из корня репозитория).' \
		'' \
		'  make setup                     первичная установка: mise install, uv sync, npm ci' \
		'  make dev                       backend + frontend одной командой (LAN по умолчанию)' \
		'  make lint                      статические проверки backend и frontend' \
		'  make test-unit                 быстрые unit-тесты + архитектурные контракты' \
		'  make test-integration          интеграционные тесты backend' \
		'  make test-affected             выбранные нативные тесты (нужны SCOPE и ARGS)' \
		'  make hooks                     установить git hooks (pre-commit, pre-push)' \
		'' \
		'  Примеры:' \
		'    make test-affected SCOPE=backend ARGS=tests/unit/test_app.py' \
		'    make test-affected SCOPE=backend ARGS="-k health"' \
		'    make test-affected SCOPE=frontend ARGS=src/App.test.tsx' \
		'' \
		'  RUN=<id>                       отдельный pytest cache для параллельных прогонов' \
		'' \
		'Подробности: README.md и docs/rules/testing.md.'

setup:
	mise install
	cd $(BACKEND) && $(MISE) uv sync
	cd $(FRONTEND) && $(MISE) npm ci

lint:
	cd $(BACKEND) && $(MISE) uv run ruff check .
	cd $(BACKEND) && $(MISE) uv run ruff format --check .
	cd $(BACKEND) && $(MISE) uv run mypy
	cd $(FRONTEND) && $(MISE) npm run lint
	cd $(FRONTEND) && $(MISE) npm run format:check
	cd $(FRONTEND) && $(MISE) npm run typecheck

test-unit:
	cd $(BACKEND) && $(MISE) uv run pytest -m unit $(PYTEST_CACHE_ARGS)
	cd $(BACKEND) && $(MISE) uv run lint-imports
	cd $(FRONTEND) && $(MISE) npm run test

test-integration:
	cd $(BACKEND) && $(MISE) uv run pytest -m integration $(PYTEST_CACHE_ARGS)

test-affected:
	@if [ -z "$(strip $(ARGS))" ]; then \
		printf '%s\n' \
			'Ошибка: ARGS пуст — передай нативные селекторы тестов.' \
			'Примеры:' \
			"  make test-affected SCOPE=backend ARGS='tests/unit/test_app.py'" \
			"  make test-affected SCOPE=backend ARGS='-k health'" \
			"  make test-affected SCOPE=frontend ARGS='src/App.test.tsx'" \
			"  make test-affected SCOPE=all ARGS='<селекторы для обоих стеков>'" >&2; \
		exit 2; \
	fi
	@case "$(SCOPE)" in \
		backend) \
			cd $(BACKEND) && $(MISE) uv run pytest $(PYTEST_CACHE_ARGS) $(ARGS) ;; \
		frontend) \
			cd $(FRONTEND) && $(MISE) npm run test -- $(ARGS) ;; \
		all) \
			( cd $(BACKEND) && $(MISE) uv run pytest $(PYTEST_CACHE_ARGS) $(ARGS) ) && \
			( cd $(FRONTEND) && $(MISE) npm run test -- $(ARGS) ) ;; \
		*) \
			printf '%s\n' "Ошибка: SCOPE=$(SCOPE) не поддерживается; допустимо backend, frontend или all." >&2; \
			exit 2 ;; \
	esac

dev:
	./scripts/dev.sh

hooks:
	@mkdir -p "$(HOOKS_DIR)"
	install -m 0755 scripts/hooks/pre-commit "$(HOOKS_DIR)/pre-commit"
	install -m 0755 scripts/hooks/pre-push "$(HOOKS_DIR)/pre-push"
	@printf 'Git hooks установлены в %s\n' "$(HOOKS_DIR)"
