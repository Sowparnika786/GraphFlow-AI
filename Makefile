.PHONY: up down build logs verify test clean

up:
	docker compose up -d

down:
	docker compose down -v

build:
	docker compose up --build -d

logs:
	docker compose logs -f

verify:
	./scripts/verify.sh

test:
	pytest tests/

clean:
	docker compose down -v
