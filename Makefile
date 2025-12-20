.PHONY: dev infra down

infra:
	docker compose up -d

down:
	docker compose down

dev:
	./scripts/dev.sh

hooks:
	pre-commit install
	pre-commit install --hook-type pre-push

