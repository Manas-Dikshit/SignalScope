dev:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build

up:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f

test:
	docker compose run --rm api pytest

migrate:
	docker compose run --rm api alembic upgrade head

shell:
	docker compose run --rm api bash
