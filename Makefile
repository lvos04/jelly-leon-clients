# Jelly Leon clients — hulpdoelen voor ontwikkelaars (Linux). Geen installatiemethode voor gebruikers.
PYTHON ?= python3.12
VENV   ?= .venv
PY      = $(VENV)/bin/python

.PHONY: help venv test lint check actionlint sync-status desktop-image desktop-bouw opruimen

help:
	@echo "make venv          - ontwikkelomgeving (pytest, ruff, actionlint, shellcheck) in $(VENV)"
	@echo "make test          - tests van de fork-tooling (nep-upstreams)"
	@echo "make lint          - ruff op tools/clients"
	@echo "make check         - forkregels: basislijn, subtrees, patchregister"
	@echo "make actionlint    - workflows controleren"
	@echo "make sync-status   - upstream-tags per client vergelijken"
	@echo "make desktop-bouw  - desktop-client bouwen en testen in een container (2 CPU's)"
	@echo "make opruimen      - bouwmap en bouwimage verwijderen"

$(VENV)/bin/python:
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install --disable-pip-version-check -r tools/clients/requirements-dev.txt

venv: $(VENV)/bin/python

test: venv
	$(PY) -m pytest -q tools/clients/tests

lint: venv
	$(VENV)/bin/ruff check --config tools/clients/ruff.toml tools/clients

check:
	python3 tools/clients/check_clients.py

actionlint: venv
	PATH="$(abspath $(VENV))/bin:$$PATH" $(VENV)/bin/actionlint .github/workflows/*.yml

sync-status:
	python3 tools/clients/upstream_sync.py status

desktop-image:
	docker build --network host --build-arg HTTPS_PROXY \
	  $(if $(CA_BUNDLE),--secret id=ca_bundle$(comma)src=$(CA_BUNDLE),) \
	  -f tools/clients/bouwverificatie/desktop.Dockerfile -t jelly-leon-clients/desktop-bouw:dev desktop/

desktop-bouw: desktop-image
	nice -n 10 tools/clients/bouwverificatie/desktop_bouw.sh

opruimen:
	rm -rf .bouw
	-docker image rm jelly-leon-clients/desktop-bouw:dev
	docker image prune -f

comma := ,
