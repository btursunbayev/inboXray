.PHONY: help install test lint format clean deploy terraform-init terraform-plan terraform-apply worker-install worker-run

help:
	@echo "Available commands:"
	@echo "  make install       - Install production dependencies"
	@echo "  make test          - Run tests with pytest"
	@echo "  make lint          - Run linting checks"
	@echo "  make format        - Format code with black"
	@echo "  make clean         - Remove cache and build files"
	@echo "  make terraform-init - Initialize Terraform"
	@echo "  make terraform-plan - Plan Terraform changes"
	@echo "  make terraform-apply - Apply Terraform changes"
	@echo "  make deploy        - Deploy Lambda function"
	@echo ""
	@echo "Phase 2 Agent Worker:"
	@echo "  make worker-install - Install agent worker dependencies"
	@echo "  make worker-run     - Run agent worker locally"

install:
	pip install -r requirements.txt

test:
	pytest tests/ -v --cov=src --cov-report=html --cov-report=term

lint:
	flake8 src/ tests/
	pylint src/

format:
	black src/ tests/
	isort src/ tests/

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".coverage" -exec rm -rf {} +
	find . -type d -name "htmlcov" -exec rm -rf {} +
	rm -f lambda_function.zip

terraform-init:
	cd terraform && terraform init

terraform-plan:
	cd terraform && terraform plan

terraform-apply:
	cd terraform && terraform apply

deploy:
	@echo "Building Lambda deployment package..."
	./scripts/deploy.sh

worker-install:
	@echo "Installing agent worker dependencies..."
	cd worker && pip install -r requirements.txt
	cd worker && playwright install chromium

worker-run:
	@echo "Starting agent worker..."
	@echo "Make sure Ollama is running and environment variables are set"
	cd worker && python agent_worker.py
