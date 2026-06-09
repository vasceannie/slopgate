.PHONY: dashboard-api dashboard-dev dashboard-build dashboard-build-local dashboard-build-ssh dashboard-prod

DASHBOARD_SSH_HOST ?= little
DASHBOARD_LOGS_DIR ?= $(HOME)/.config/slopgate/logs

dashboard-api:
	python3 dashboard/scripts/serve.py

dashboard-dev:
	npm --prefix dashboard run dev

dashboard-build dashboard-build-local:
	python3 dashboard/scripts/build-standalone.py --logs-dir $(DASHBOARD_LOGS_DIR)

dashboard-build-ssh:
	python3 dashboard/scripts/build-standalone.py --ssh $(DASHBOARD_SSH_HOST)

dashboard-prod: dashboard-build-ssh dashboard-api
