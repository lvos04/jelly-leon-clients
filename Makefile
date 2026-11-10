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

.PHONY: help venv test lint check actionlint sync-status android-bouw androidtv-bouw desktop-image desktop-bouw opruimen \
        release-apks emulator-image desktop-test-image compat-android compat-desktop compat-swiftfin

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
	@echo ""
	@echo "Compatibiliteit met de Jelly Leon 12.x-server (P4-0, JC3; ADR-0011) — alleen ontwikkeling, lokaal:"
	@echo "make release-apks      - release-APK's van de fork-apps zonder handtekening (eigen applicationId)"
	@echo "make emulator-image    - runner-image voor de emulator (alleen bibliotheken; SDK wordt gekoppeld)"
	@echo "make desktop-test-image - desktop-bouwomgeving + Xvfb/QML-runtime (doel 'test')"
	@echo "make compat-android JL_IMAGE=<jelly-leon-image>  - emulatortests (KVM; stack.lock + gradle.lock)"
	@echo "make compat-desktop JL_IMAGE=<jelly-leon-image> DESKTOP_BUILD=<map> - desktop onder Xvfb"
	@echo "make compat-swiftfin JL_IMAGE=<jelly-leon-image> - serverkant van het Swiftfin-protocol"

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

# Officiële upstream-APK's voor `app_identiteit.py vergelijk` (sha256-gepind; hergebruikt of gedownload).
OFFICIELE_APKS ?= .bouw/officiele-apks
# Release-resources linken (manifest + resources, geen release-APK) zodat aapt2 ook de release-ID controleert.
RELEASE_RES_android = processLibreReleaseResources processProprietaryReleaseResources
RELEASE_RES_androidtv = processReleaseResources

android-bouw androidtv-bouw: %-bouw:
	@test -n "$$ANDROID_HOME" || { echo "ANDROID_HOME is niet gezet (Android SDK met platform 36)"; exit 2; }
	cd $* && $(GRADLE) assembleDebug test $(RELEASE_RES_$*)
	python3 tools/clients/app_identiteit.py bouwmap $* $*/app/build --verwacht debug,release
	python3 tools/clients/app_identiteit.py vergelijk $* $*/app/build --officieel-map $(OFFICIELE_APKS)

desktop-image:
	nice -n 10 $(if $(DOCKER_LOCK),flock $(DOCKER_LOCK)) docker buildx build --load \
	  $(if $(CA_BUNDLE),--secret id=ca_bundle$(comma)src=$(CA_BUNDLE),) \
	  -f tools/clients/bouwverificatie/desktop.Dockerfile -t jelly-leon-clients/desktop-bouw:dev desktop/

desktop-bouw: desktop-image
	nice -n 10 $(if $(DOCKER_LOCK),flock $(DOCKER_LOCK)) tools/clients/bouwverificatie/desktop_bouw.sh

# --- compatibiliteit 12.x (JC3) -------------------------------------------------------------------------------
JL_IMAGE ?=
DESKTOP_BUILD ?= .bouw/desktop
RELEASE_android = assembleLibreRelease -Pjellyfin.version=2.7.3-jl.1
RELEASE_androidtv = assembleRelease -Pjellyfin.version=0.19.10-jl.1

release-apks:
	@test -n "$$ANDROID_HOME" || { echo "ANDROID_HOME is niet gezet (Android SDK met platform 36)"; exit 2; }
	cd android && $(GRADLE) $(RELEASE_android)
	cd androidtv && $(GRADLE) $(RELEASE_androidtv)

emulator-image:
	nice -n 10 $(if $(DOCKER_LOCK),flock $(DOCKER_LOCK)) docker buildx build --load \
	  -f tools/clients/compat/emulator.Dockerfile -t jelly-leon-clients/emulator-runner:dev tools/clients/compat

desktop-test-image:
	nice -n 10 $(if $(DOCKER_LOCK),flock $(DOCKER_LOCK)) docker buildx build --load --target test \
	  -f tools/clients/bouwverificatie/desktop.Dockerfile -t jelly-leon-clients/desktop-test:dev desktop/

compat-android:
	@test -n "$(JL_IMAGE)" || { echo "zet JL_IMAGE=<jelly-leon-image>"; exit 2; }
	python3 tools/clients/client_compat.py android --image $(JL_IMAGE)

compat-desktop:
	@test -n "$(JL_IMAGE)" || { echo "zet JL_IMAGE=<jelly-leon-image>"; exit 2; }
	python3 tools/clients/client_compat.py desktop --met-stock --image $(JL_IMAGE) --build $(DESKTOP_BUILD)

compat-swiftfin:
	@test -n "$(JL_IMAGE)" || { echo "zet JL_IMAGE=<jelly-leon-image>"; exit 2; }
	python3 tools/clients/client_compat.py swiftfin --image $(JL_IMAGE)

opruimen:
	rm -rf .bouw
	rm -rf android/build android/app/build android/buildSrc/build android/.gradle android/buildSrc/.gradle android/.kotlin
	rm -rf androidtv/build androidtv/app/build androidtv/preference/build androidtv/playback/*/build \
	  androidtv/playback/media3/*/build androidtv/buildSrc/build androidtv/.gradle androidtv/buildSrc/.gradle \
	  androidtv/.kotlin
	-docker image rm jelly-leon-clients/desktop-bouw:dev jelly-leon-clients/desktop-test:dev \
	  jelly-leon-clients/emulator-runner:dev
	docker image prune -f

comma := ,
