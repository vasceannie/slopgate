.PHONY: dashboard-api dashboard-dev dashboard-build dashboard-build-local dashboard-build-ssh dashboard-prod publish

DASHBOARD_SSH_HOST ?= little
DASHBOARD_LOGS_DIR ?= $(HOME)/.config/slopgate/logs
-include .env

UV_PUBLISH_TOKEN ?= $(PYPI_TOKEN)

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

publish:
	@CURRENT=$$(cut -d'"' -f2 $(VERSION_FILE)); \
	MAJ=$$(echo "$$CURRENT" | cut -d. -f1); \
	MIN=$$(echo "$$CURRENT" | cut -d. -f2); \
	PAT=$$(echo "$$CURRENT" | cut -d. -f3); \
	case "$(BUMP)" in \
		major) NEW="$$((MAJ + 1)).0.0" ;; \
		minor) NEW="$$MAJ.$$((MIN + 1)).0" ;; \
		*)     NEW="$$MAJ.$$MIN.$$((PAT + 1))" ;; \
	esac; \
	echo "Bumping $$CURRENT → $$NEW"; \
	echo "__version__ = \"$$NEW\"" > $(VERSION_FILE); \
	git add $(VERSION_FILE); \
	git commit -m "Bump version to $$NEW"; \
	git tag -a "v$$NEW" -m "Release v$$NEW"; \
	git push origin v$$NEW; \
	git push github v$$NEW; \
	echo "Pushed tag v$$NEW to origin and github"; \
	echo "Building and publishing to PyPI..."; \
	rm -rf dist; \
	uv build; \
	uv publish --token $(UV_PUBLISH_TOKEN); \
	echo "Done. v$$NEW is live on PyPI."
