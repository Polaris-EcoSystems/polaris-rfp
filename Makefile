.PHONY: dev infra down

infra:
	docker compose up -d

down:
	docker compose down

dev:
	./scripts/dev.sh

