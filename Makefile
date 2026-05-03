.PHONY: install install-dev test lint build clean \
        install-py install-py-dev test-py lint-py build-py \
        install-js test-js build-js

# ── Python ────────────────────────────────────────────────────────────────────

install-py:
	pip install -e packages/python/core
	pip install -e packages/python/openai
	pip install -e packages/python/openai_agents
	pip install -e packages/python/claude_code

install-py-dev: install-py
	pip install pytest pytest-asyncio ruff mypy

test-py:
	pytest packages/python/core/tests -v
	pytest packages/python/openai/tests -v
	pytest packages/python/openai_agents/tests -v
	pytest packages/python/claude_code/tests -v

lint-py:
	ruff check packages/python/
	ruff format --check packages/python/

format-py:
	ruff format packages/python/

build-py:
	cd packages/python/core && python -m build
	cd packages/python/openai && python -m build
	cd packages/python/openai_agents && python -m build
	cd packages/python/claude_code && python -m build

# ── JavaScript ────────────────────────────────────────────────────────────────

install-js:
	npm install --prefix packages/js

test-js:
	npm test --workspaces --prefix packages/js

build-js:
	npm run build --workspaces --prefix packages/js

# ── Combined shortcuts ────────────────────────────────────────────────────────

install: install-py install-js
install-dev: install-py-dev install-js
test: test-py test-js
lint: lint-py

# Clean build artifacts
clean:
	rm -rf packages/python/*/dist
	rm -rf packages/python/*/build
	rm -rf packages/python/*/*.egg-info
	rm -rf packages/python/*/src/*.egg-info
	rm -rf packages/js/*/node_modules
	rm -rf packages/js/node_modules
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
