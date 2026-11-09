# Jelly Leon clients — hulpdoelen voor ontwikkelaars (Linux). Geen installatiemethode voor gebruikers.
PYTHON ?= python3.12
VENV   ?= .venv
PY      = $(VENV)/bin/python
# Optioneel: lockbestanden om zware stappen met andere bouwers op dezelfde machine te serialiseren (flock).
GRADLE_LOCK ?=
DOCKER_LOCK ?=
GRADLE_WORKERS ?= 4
GRADLE_HEAP ?= 2g
GRADLE  = nice -n 10 $(if $(GRADLE_LOCK),flock $(GRADLE_LOCK)) ./gradlew --no-daemon --max-workers=$(GRADLE_WORKERS) \
          -Dorg.gradle.jvmargs=-Xmx$(GRADLE_HEAP)

.PHONY: help venv test lint check actionlint sync-status android-bouw androidtv-bouw desktop-image desktop-bouw opruimen

help:
	@echo "make venv          - ontwikkelomgeving (pytest, ruff, actionlint, shellcheck) in $(VENV)"
	@echo "make test          - tests van de fork-tooling (nep-upstreams)"
	@echo "make lint          - ruff op tools/clients"
	@echo "make check         - forkregels (basislijn, subtrees, patchregister) en eigen app-identiteit in de bron"
	@echo "make actionlint    - workflows controleren"
	@echo "make sync-status   - upstream-tags per client vergelijken"
	@echo "make android-bouw  - android: debug-APK's + unit-tests + aapt2-controle app-identiteit (JDK 21, ANDROID_HOME)"
	@echo "make androidtv-bouw - androidtv: debug-APK + unit-tests + aapt2-controle app-identiteit (JDK 21, ANDROID_HOME)"
	@echo "make desktop-bouw  - desktop-client bouwen en testen in een container (2 CPU's, JOBS=n voor meer)"
	@echo "                     optioneel: GRADLE_LOCK=<bestand> / DOCKER_LOCK=<bestand> (flock)"
	@echo "make opruimen      - bouwmappen (.bouw, Gradle) en bouwimage verwijderen"

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
	python3 tools/clients/app_identiteit.py bron

actionlint: venv
	PATH="$(abspath $(VENV))/bin:$$PATH" $(VENV)/bin/actionlint .github/workflows/*.yml

sync-status:
	python3 tools/clients/upstream_sync.py status

# Release-resources linken (manifest + resources, geen release-APK) zodat aapt2 ook de release-ID controleert.
RELEASE_RES_android = processLibreReleaseResources processProprietaryReleaseResources
RELEASE_RES_androidtv = processReleaseResources

android-bouw androidtv-bouw: %-bouw:
	@test -n "$$ANDROID_HOME" || { echo "ANDROID_HOME is niet gezet (Android SDK met platform 36)"; exit 2; }
	cd $* && $(GRADLE) assembleDebug test $(RELEASE_RES_$*)
	python3 tools/clients/app_identiteit.py bouwmap $* $*/app/build --verwacht debug,release

desktop-image:
	nice -n 10 $(if $(DOCKER_LOCK),flock $(DOCKER_LOCK)) docker buildx build --load \
	  $(if $(CA_BUNDLE),--secret id=ca_bundle$(comma)src=$(CA_BUNDLE),) \
	  -f tools/clients/bouwverificatie/desktop.Dockerfile -t jelly-leon-clients/desktop-bouw:dev desktop/

desktop-bouw: desktop-image
	nice -n 10 $(if $(DOCKER_LOCK),flock $(DOCKER_LOCK)) tools/clients/bouwverificatie/desktop_bouw.sh

opruimen:
	rm -rf .bouw
	rm -rf android/build android/app/build android/buildSrc/build android/.gradle android/buildSrc/.gradle android/.kotlin
	rm -rf androidtv/build androidtv/app/build androidtv/preference/build androidtv/playback/*/build \
	  androidtv/playback/media3/*/build androidtv/buildSrc/build androidtv/.gradle androidtv/buildSrc/.gradle \
	  androidtv/.kotlin
	-docker image rm jelly-leon-clients/desktop-bouw:dev
	docker image prune -f

comma := ,
