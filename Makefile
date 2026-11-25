COMPOSE = docker compose -f deploy/docker-compose.yaml --env-file .env

.PHONY: up down logs rebuild rebuild-full ps shell test

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down --rmi local

logs:
	$(COMPOSE) logs -f --tail 1000

rebuild: down up

rebuild-full:
	$(COMPOSE) build --no-cache --pull backend
	$(COMPOSE) up -d --force-recreate

test:
	$(COMPOSE) exec backend python test_youtube.py $(URL)

ps:
	$(COMPOSE) ps

shell:
	$(COMPOSE) exec backend bash