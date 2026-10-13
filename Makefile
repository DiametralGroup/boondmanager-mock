SHELL := /bin/bash
.DEFAULT_GOAL := help
UV := uv

.PHONY: help bootstrap test lint format run image up contract

help:        ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

bootstrap:   ## Resolve and install the environment
	$(UV) sync

test:        ## pytest — dialect, 22 collections, incremental evolution, failure modes
	$(UV) run pytest tests/ -W ignore::DeprecationWarning

lint:        ## ruff + strict mypy
	$(UV) run ruff check .
	$(UV) run ruff format --check .
	$(UV) run mypy src/boondmanager_mock

format:      ## Format the code
	$(UV) run ruff format .
	$(UV) run ruff check --fix .

run:         ## Run the mock locally (admin plane open)
	BOOND_MOCK_ADMIN_ENABLED=true $(UV) run python -m boondmanager_mock

image:       ## Build the container image
	docker build -t boondmanager-mock:dev .

up:          ## Run the mock in a container (docker compose up --build)
	docker compose up --build

contract:    ## Regenerate contracts/boondmanager.openapi.yaml from the app
	@# `contract_openapi()` rather than `app.openapi()`: the contract describes the
	@# BoondManager DIALECT. /__admin and /__fixtures are mock affordances —
	@# publishing them would pass off as vendor API what is not, and /__admin is
	@# only mounted conditionally, which would make the contract depend on the
	@# generation environment.
	$(UV) run python -c "import yaml, boondmanager_mock as m; \
open('contracts/boondmanager.openapi.yaml','w').write(yaml.safe_dump(m.contract_openapi(), sort_keys=False, allow_unicode=True))"
	@echo "✓ contract regenerated — REVIEW the diff: a changed response shape is a contract change for consumers"
