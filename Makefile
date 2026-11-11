.PHONY: help install install-dev install-py install-py-dev install-js \
        test test-py test-js test-all lint lint-py format-py build build-py build-js \
        clean healthcheck healthcheck-quick

# Default target: display help
help:
	@echo "================================================================================"
	@echo "                   AnoSys SDK Developer Shortcuts                               "
	@echo "================================================================================"
	@echo "  make install-dev       - Install all Python & JS packages for local development"
	@echo "  make test              - Run Python and JS unit test suites"
	@echo "  make test-all          - Run all 7 SDK verification suites (test/run_all_tests.sh)"
	@echo "  make healthcheck       - Run the release health check (testcases/run_all.sh)"
	@echo "  make healthcheck-quick - Quick health check: lint, static, leaks, levels"
	@echo "  make lint              - Lint Python packages with ruff"
	@echo "  make format-py         - Auto-format Python packages with ruff"
	@echo "  make build             - Build distribution wheels/tarballs for Python and JS"
	@echo "  make clean             - Remove all build artifacts, cache, and temp files"
	@echo "================================================================================"

# ── Python ────────────────────────────────────────────────────────────────────

install-py:
	pip install -e packages/python/core
	pip install -e packages/python/openai
	pip install -e packages/python/openai_agents
	pip install -e packages/python/claude_code
	pip install -e packages/python/codex
	pip install -e packages/python/anthropic
	pip install --no-deps -e packages/python/claude_agents 2>/dev/null || pip install -e packages/python/claude_agents
	pip install -e packages/python/antigravity

install-py-dev: install-py
	pip install pytest pytest-asyncio pytest-cov ruff mypy cryptography requests python-dotenv opentelemetry-api opentelemetry-sdk

test-py:
	env -u ANOSYS_ENCRYPTION_KEY -u ANOSYS_ENCRYPTION_SALT -u CODEX_HOME pytest packages/python -v

lint-py:
	ruff check packages/python/
	ruff format --check packages/python/

format-py:
	ruff format packages/python/

build-py:
	@for pkg in packages/python/*; do \
		if [ -f "$$pkg/pyproject.toml" ]; then \
			echo "Building $$pkg..."; \
			(cd "$$pkg" && python -m build) || exit 1; \
		fi \
	done

# ── JavaScript ────────────────────────────────────────────────────────────────

install-js:
	npm install --prefix packages/js

test-js:
	env -u ANOSYS_ENCRYPTION_KEY -u ANOSYS_ENCRYPTION_SALT npm test --workspaces --prefix packages/js

build-js:
	npm run build --workspaces --if-present --prefix packages/js

# ── Combined Shortcuts ────────────────────────────────────────────────────────

install: install-py install-js
install-dev: install-py-dev install-js
test: test-py test-js
lint: lint-py
build: build-py build-js

# Clean build artifacts, temporary caches, and test outputs
clean:
	rm -rf packages/python/*/dist
	rm -rf packages/python/*/build
	rm -rf packages/python/*/*.egg-info
	rm -rf packages/python/*/src/*.egg-info
	rm -rf packages/js/*/node_modules
	rm -rf packages/js/node_modules
	rm -rf testcases/.results
	rm -rf .coverage htmlcov
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true

# ── Release health check (testcases/) ─────────────────────────────────────────

healthcheck:
	testcases/run_all.sh

healthcheck-quick:
	testcases/run_all.sh --quick

test-all:
	bash test/run_all_tests.sh
