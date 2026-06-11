.PHONY: dashboard-api dashboard-dev dashboard-build dashboard-build-local dashboard-build-ssh dashboard-prod publish bump

SHELL := /bin/bash
.SHELLFLAGS := -euo pipefail -c

DASHBOARD_SSH_HOST ?= little
DASHBOARD_LOGS_DIR ?= $(HOME)/.config/slopgate/logs
-include .env

export UV_PUBLISH_TOKEN ?= $(PYPI_TOKEN)

dashboard-api:
	python3 dashboard/scripts/serve.py

dashboard-dev:
	npm --prefix dashboard run dev

dashboard-build dashboard-build-local:
	python3 dashboard/scripts/build-standalone.py --logs-dir $(DASHBOARD_LOGS_DIR)

dashboard-build-ssh:
	python3 dashboard/scripts/build-standalone.py --ssh $(DASHBOARD_SSH_HOST)

dashboard-prod: dashboard-build-ssh dashboard-api

VERSION_FILE := src/slopgate/_version.py

bump:
	@CURRENT=$$(cut -d'"' -f2 $(VERSION_FILE)); \
	[ -n "$$CURRENT" ] || { echo "ERROR: could not read version from $(VERSION_FILE)"; exit 1; }; \
	case "${BUMP}" in \
		""|major|minor|patch) ;; \
		*) echo "ERROR: BUMP must be major, minor, or patch"; exit 1 ;; \
	esac; \
	MAJ=$$(echo "$$CURRENT" | cut -d. -f1); \
	MIN=$$(echo "$$CURRENT" | cut -d. -f2); \
	PAT=$$(echo "$$CURRENT" | cut -d. -f3); \
	case "${BUMP}" in \
		major) NEW="$$((MAJ + 1)).0.0" ;; \
		minor) NEW="$$MAJ.$$((MIN + 1)).0" ;; \
		*)     NEW="$$MAJ.$$MIN.$$((10#$$PAT + 1))" ;; \
	esac; \
	echo "Bumping $$CURRENT → $$NEW"; \
	echo "__version__ = \"$$NEW\"" > $(VERSION_FILE); \
	git add $(VERSION_FILE); \
	git commit -m "Bump version to $$NEW"; \
	git tag -f "v$$NEW" -m "Release v$$NEW"; \
	echo "Bump done. v$$NEW is committed and tagged locally."

publish:
	@: "$${UV_PUBLISH_TOKEN:?ERROR: UV_PUBLISH_TOKEN is not set. Add PYPI_TOKEN=... to .env}"; \
	CURRENT=$$(cut -d'"' -f2 $(VERSION_FILE)); \
	[ -n "$$CURRENT" ] || { echo "ERROR: could not read version from $(VERSION_FILE)"; exit 1; }; \
	case "${BUMP}" in \
		""|major|minor|patch) ;; \
		*) echo "ERROR: BUMP must be major, minor, or patch"; exit 1 ;; \
	esac; \
	MAJ=$$(echo "$$CURRENT" | cut -d. -f1); \
	MIN=$$(echo "$$CURRENT" | cut -d. -f2); \
	PAT=$$(echo "$$CURRENT" | cut -d. -f3); \
	case "${BUMP}" in \
		major) NEW="$$((MAJ + 1)).0.0" ;; \
		minor) NEW="$$MAJ.$$((MIN + 1)).0" ;; \
		*)     NEW="$$MAJ.$$MIN.$$((10#$$PAT + 1))" ;; \
	esac; \
	echo "Bumping $$CURRENT → $$NEW"; \
	echo "__version__ = \"$$NEW\"" > $(VERSION_FILE); \
	echo "Building..."; \
	rm -rf dist; \
	uv build; \
	uv publish; \
	git add $(VERSION_FILE); \
	git commit -m "Bump version to $$NEW"; \
	git tag -f "v$$NEW" -m "Release v$$NEW"; \
	BRANCH=$$(git rev-parse --abbrev-ref HEAD); \
	git push origin v$$NEW && git push github v$$NEW; \
	git push origin $$BRANCH && git push github $$BRANCH; \
	echo "Done. v$$NEW is live on PyPI."
