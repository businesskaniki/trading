.PHONY: help backend-test frontend-build compile smoke check docker-config

PYTHON ?= python

help:
	@echo "Athena Quant Engine commands:"
	@echo "  make backend-test    Run backend pytest suite"
	@echo "  make frontend-build  Build the Vite frontend"
	@echo "  make compile         Compile backend, engine, services, scripts, strategies"
	@echo "  make smoke           Run local smoke checks without external services"
	@echo "  make check           Run backend-test, compile, smoke, frontend-build"
	@echo "  make docker-config   Validate Docker Compose config when Docker is installed"

backend-test:
	cd backend && pytest -q

frontend-build:
	cd frontend && npm run build

compile:
	SECRET_KEY=x POSTGRES_HOST=localhost POSTGRES_DB=db POSTGRES_USER=user POSTGRES_PASSWORD=pass REDIS_HOST=localhost SMTP_HOST=localhost SMTP_USERNAME=u SMTP_PASSWORD=p SMTP_FROM_EMAIL=test@example.com $(PYTHON) -m py_compile $$(find backend/app engine services scripts strategies -name '*.py' | sort)

smoke:
	$(PYTHON) scripts/smoke_test.py

check: backend-test compile smoke frontend-build

docker-config:
	docker compose -f infrastructure/docker-compose.yml config
