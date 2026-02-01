.PHONY: install install-dev test lint build clean

# Install all packages in development mode
install:
	pip install -e packages/core
	pip install -e packages/openai
	pip install -e packages/openai_agents

# Install with dev dependencies
install-dev: install
	pip install pytest pytest-asyncio ruff mypy

# Run tests for all packages
test:
	pytest packages/core/tests -v
	pytest packages/openai/tests -v
	pytest packages/openai_agents/tests -v

# Run linting
lint:
	ruff check packages/
	ruff format --check packages/

# Format code
format:
	ruff format packages/

# Build all packages
build:
	cd packages/core && python -m build
	cd packages/openai && python -m build
	cd packages/openai_agents && python -m build

# Clean build artifacts
clean:
	rm -rf packages/*/dist
	rm -rf packages/*/build
	rm -rf packages/*/*.egg-info
	rm -rf packages/*/src/*.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
