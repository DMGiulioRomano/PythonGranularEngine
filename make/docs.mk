# make/docs.mk — Diátaxis docs tooling

DOCS_PYTHON := $(VENV_DIR)/bin/python

.PHONY: docs-index docs-index-check docs-lint docs-hooks

docs-index: venv-setup
	$(DOCS_PYTHON) utils/build_docs_index.py

docs-index-check: venv-setup
	$(DOCS_PYTHON) utils/build_docs_index.py --check

docs-lint: venv-setup
	$(DOCS_PYTHON) utils/lint_docs.py

docs-hooks:
	@cp utils/pre-commit-docs .git/hooks/pre-commit
	@chmod +x .git/hooks/pre-commit
	@echo "installed pre-commit hook -> .git/hooks/pre-commit"
