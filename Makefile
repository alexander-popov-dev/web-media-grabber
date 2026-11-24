COMPOSE = docker compose -f deploy/docker-compose.yaml --env-file .env
COMPOSE_MONITORING = docker compose -f monitoring/docker-compose.yaml --env-file .env

.PHONY: up stop down logs rebuild \
	up-app stop-app down-app logs-app rebuild-app \
	up-db stop-db down-db logs-db\
	up-backend stop-backend down-backend logs-backend rebuild-backend\
	up-frontend stop-frontend down-frontend logs-frontend rebuild-frontend\
	up-bots stop-bots down-bots logs-bots rebuild-bots

# All services
up:
	$(COMPOSE) --profile db --profile backend --profile bots --profile frontend up -d

stop:
	$(COMPOSE) --profile db --profile backend --profile bots --profile frontend stop

down:
	$(COMPOSE) --profile db --profile backend --profile bots --profile frontend down --rmi local

logs:
	$(COMPOSE) logs -f --tail 1000

rebuild: down up

# Backend service
up-backend:
	$(COMPOSE) --profile backend up -d backend

stop-backend:
	$(COMPOSE) --profile backend stop backend

down-backend:
	$(COMPOSE) --profile backend down backend --rmi local

logs-backend:
	$(COMPOSE) logs -f --tail 1000 backend

rebuild-backend: down-backend up-backend

# Database services
up-db:
	$(COMPOSE) --profile db up -d postgres redis

stop-db:
	$(COMPOSE) --profile db stop postgres redis

down-db:
	$(COMPOSE) --profile db down postgres redis --rmi local

logs-db:
	$(COMPOSE) logs -f --tail 1000 postgres redis

rebuild-db: down-db up-db

# Bots
up-bots:
	$(COMPOSE) --profile bots up -d admin-bot

stop-bots:
	$(COMPOSE) --profile bots stop admin-bot

down-bots:
	$(COMPOSE) --profile bots down admin-bot --rmi local

logs-bots:
	$(COMPOSE) logs -f --tail 1000 admin-bot

rebuild-bots: down-bots up-bots

# Frontend (placeholder for future)
up-frontend:
	@echo "Frontend service not yet implemented"

stop-frontend:
	@echo "Frontend service not yet implemented"

down-frontend:
	@echo "Frontend service not yet implemented"

logs-frontend:
	@echo "Frontend service not yet implemented"

rebuild-frontend: down-frontend up-frontend

# Application (backend + db)
up-app:
	$(COMPOSE) --profile backend --profile db up -d

stop-app:
	$(COMPOSE) --profile backend --profile db stop

down-app:
	$(COMPOSE) --profile backend --profile db down --rmi local

logs-app:
	$(COMPOSE) logs -f --tail 1000 backend postgres redis

rebuild-app: down-app up-app

# Development helpers
dev:
	$(COMPOSE) --profile db --profile backend up -d && $(COMPOSE) logs -f backend

# Build images
build:
	$(COMPOSE) build

build-backend:
	$(COMPOSE) build backend

# Clean up
clean:
	$(COMPOSE) down -v --rmi all --remove-orphans

prune:
	docker system prune -f

# Deploy to production (pull latest images, rebuild, restart)
deploy:
	git pull origin main
	$(COMPOSE) build --pull
	$(COMPOSE) --profile db --profile backend --profile bots up -d --force-recreate
	$(COMPOSE) image prune -f

# Show status
ps:
	$(COMPOSE) ps

# Shell access
shell-backend:
	$(COMPOSE) exec backend bash

shell-db:
	$(COMPOSE) exec postgres psql -U postgres

shell-redis:
	$(COMPOSE) exec redis redis-cli

# View environment
env:
	@cat .env

# Help
help:
	@echo "Available targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# Default target
.DEFAULT_GOAL := help