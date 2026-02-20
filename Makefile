.PHONY: help login install deploy clean test

# Load environment variables from .env
ifneq (,$(wildcard .env))
    include .env
    export
endif

help:
	@echo "inboXray - Email Security System"
	@echo ""
	@echo "Commands:"
	@echo "  make login      - Configure AWS CLI from .env credentials"
	@echo "  make install    - Install dependencies"
	@echo "  make deploy     - Deploy to AWS"
	@echo "  make test       - Run tests"
	@echo "  make clean      - Clean build artifacts"

# Configure AWS CLI using credentials from .env
login:
	@if [ -z "$(AWS_ACCESS_KEY_ID)" ] || [ -z "$(AWS_SECRET_ACCESS_KEY)" ]; then \
		echo "Error: AWS_ACCESS_KEY_ID or AWS_SECRET_ACCESS_KEY not found in .env"; \
		exit 1; \
	fi
	@aws configure set aws_access_key_id $(AWS_ACCESS_KEY_ID)
	@aws configure set aws_secret_access_key $(AWS_SECRET_ACCESS_KEY)
	@aws configure set region $(AWS_REGION)
	@aws configure set output json
	@echo "AWS CLI configured (region: $(AWS_REGION))"
	@aws sts get-caller-identity --query '[Account,Arn]' --output table

# Install dependencies
install:
	@echo "Installing dependencies..."
	@pip install -r requirements.txt
	@echo "Done."

# Deploy to AWS
deploy:
	@./scripts/deploy.sh

test:
	python -m pytest tests/unit/ -v --cov=src --cov-report=term-missing

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -f lambda_function.zip
