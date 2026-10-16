ifneq (,$(wildcard .venv/bin/python))
PYTHON := .venv/bin/python
else
PYTHON := python3
endif

.PHONY: test check setup destroy

test:
	$(PYTHON) -m pytest -q

check:
	$(PYTHON) -m sql_demo check

setup:
	$(PYTHON) -m sql_demo setup

destroy:
	$(PYTHON) -m sql_demo destroy
