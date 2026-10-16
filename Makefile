ifneq (,$(wildcard .venv/bin/python))
PYTHON := .venv/bin/python
else
PYTHON := python3
endif

.PHONY: test setup destroy

test:
	$(PYTHON) -m pytest -q

setup:
	$(PYTHON) -m sql_demo setup

destroy:
	$(PYTHON) -m sql_demo destroy
