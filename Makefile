COMPOSE = docker compose -f deploy/docker-compose.yaml --env-file .env

.PHONY: up down logs rebuild ps shell

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down --rmi local

logs:
	$(COMPOSE) logs -f --tail 1000

rebuild: down up

ps:
	$(COMPOSE) ps

shell:
	$(COMPOSE) exec backend bash