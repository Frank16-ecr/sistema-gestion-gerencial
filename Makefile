.PHONY: help install install-dev migrate run test pytest coverage lint format docker-up docker-down docker-logs shell

PYTHON   = python
MANAGE   = $(PYTHON) manage.py
TEST_SETTINGS = sgg.test_settings

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ── Development ───────────────────────────────────────────────────────────────

install: ## Install Python dependencies
	pip install -r requirements.txt

install-dev: ## Install development dependencies (tests, lint)
	pip install -r requirements-dev.txt

migrate: ## Run database migrations
	$(MANAGE) migrate

migrations: ## Create new migrations
	$(MANAGE) makemigrations

run: ## Start the Django development server
	$(MANAGE) runserver

shell: ## Open Django shell
	$(MANAGE) shell

superuser: ## Create a Django superuser
	$(MANAGE) createsuperuser

collectstatic: ## Collect static files
	$(MANAGE) collectstatic --noinput

# ── Testing & Linting ─────────────────────────────────────────────────────────

test: ## Run the test suite (uses SQLite in-memory)
	$(MANAGE) test tests/ --settings=$(TEST_SETTINGS) --verbosity=2

pytest: ## Run the test suite with pytest
	pytest

coverage: ## Run tests with coverage report
	coverage run -m pytest && coverage report --skip-covered

check: ## Run Django system checks
	$(MANAGE) check

lint: ## Run flake8 linter
	flake8 .

isort: ## Sort imports with isort
	isort .

isort-check: ## Check import ordering without modifying files
	isort --check-only --diff .

format: isort lint ## Format code and check linting

# ── Celery ────────────────────────────────────────────────────────────────────

worker: ## Start Celery worker
	celery -A sgg worker -l info

beat: ## Start Celery Beat scheduler
	celery -A sgg beat -l info

# ── Docker ────────────────────────────────────────────────────────────────────

docker-build: ## Build Docker images
	docker compose build

docker-up: ## Start all services with Docker Compose
	docker compose up -d

docker-down: ## Stop all Docker Compose services
	docker compose down

docker-logs: ## Tail Docker Compose logs
	docker compose logs -f

docker-test: ## Run tests inside the Docker web container
	docker compose run --rm web python manage.py test tests/ \
	  --settings=$(TEST_SETTINGS) --verbosity=2

docker-migrate: ## Run migrations inside Docker
	docker compose exec web python manage.py migrate

docker-superuser: ## Create superuser inside Docker
	docker compose exec web python manage.py createsuperuser
