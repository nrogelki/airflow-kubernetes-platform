# Airflow KubernetesExecutor platform — entry point for every operation.
# `make help` lists the targets. Configuration: config/platform.env

SHELL := /bin/bash
.DEFAULT_GOAL := help
# Read a variable from config/platform.env through the shell (the file uses
# shell syntax with quotes, so it must not be included as a makefile).
env_get = $(shell [ -f config/platform.env ] && . ./config/platform.env; printf '%s' "$${$(1)}")
KUBECTL := $(or $(call env_get,KUBECTL),microk8s kubectl)
AIRFLOW_NAMESPACE := $(or $(call env_get,AIRFLOW_NAMESPACE),airflow)
HELM_RELEASE := $(or $(call env_get,HELM_RELEASE),airflow)
SERVER_IP := $(or $(call env_get,SERVER_IP),$(shell hostname -I 2>/dev/null | awk '{print $$1}'))
NODE_PORT := $(or $(call env_get,NODE_PORT),31399)

.PHONY: help
help: ## Show this help
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage: make \033[36m<target>\033[0m\n"} /^[a-zA-Z0-9_-]+:.*?##/ { printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2 } /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) }' $(MAKEFILE_LIST)

##@ Setup (one time)
.PHONY: init
init: ## Create config/platform.env from the example (never overwrites)
	@if [ -f config/platform.env ]; then echo "config/platform.env already exists"; \
	else cp config/platform.env.example config/platform.env && chmod 640 config/platform.env && \
	echo "Created config/platform.env -> edit it, then run 'make render'"; fi

.PHONY: install-microk8s
install-microk8s: ## Install MicroK8s (pinned) + addons [sudo]
	sudo scripts/install_microk8s.sh $(ARGS)

.PHONY: install-helm
install-helm: ## Install pinned Helm binary [sudo]
	sudo scripts/install_helm.sh

.PHONY: bootstrap
bootstrap: ## Create runtime dirs, group and permissions on the node [sudo]
	sudo -E scripts/bootstrap_host.sh

.PHONY: conda-env
conda-env: ## Create/update the isolated env from envs/<env>/environment.yml [ARGS=--recreate] [sudo]
	sudo -E scripts/create_conda_env.sh $(ARGS)

.PHONY: repair-env
repair-env: ## Reinstall every package of the env at the locked versions [sudo]
	sudo -E scripts/repair_conda_env.sh

##@ Build & deploy
.PHONY: render
render: ## Render helm/values.yaml + pod_template.yaml from config/platform.env
	scripts/render_config.sh

.PHONY: build
build: ## Build the Airflow image and import it into MicroK8s containerd
	scripts/build_image.sh

.PHONY: deploy
deploy: render ## helm upgrade --install with the rendered values
	scripts/deploy.sh

.PHONY: deploy-dry-run
deploy-dry-run: render ## Render the Helm release without applying it
	scripts/deploy.sh --dry-run

.PHONY: cronjobs
cronjobs: ## Apply the self-healing CronJobs (pod cleaner + Calico watchdog)
	$(KUBECTL) apply -k k8s/cronjobs/

.PHONY: test-watchdog
test-watchdog: ## Run the Calico watchdog test suite (prepare + all + finish)
	k8s/cronjobs/scripts/test-watchdog.sh prepare
	k8s/cronjobs/scripts/test-watchdog.sh all; rc=$$?; k8s/cronjobs/scripts/test-watchdog.sh finish; exit $$rc

.PHONY: all
all: render build deploy ## render + build + deploy

##@ Operation
.PHONY: status
status: ## Pods of the Airflow namespace
	$(KUBECTL) get pods -n $(AIRFLOW_NAMESPACE) -o wide

.PHONY: doctor
doctor: ## Health check of host, cluster and Airflow
	scripts/doctor.sh

.PHONY: ui-url
ui-url: ## Print the Airflow UI URL
	@echo "http://$(SERVER_IP):$(NODE_PORT)"

.PHONY: restart-scheduler
restart-scheduler: ## Reload pod_template.yaml / new DAG folders
	$(KUBECTL) rollout restart deployment $(HELM_RELEASE)-scheduler -n $(AIRFLOW_NAMESPACE)

.PHONY: logs-scheduler
logs-scheduler: ## Tail scheduler logs
	$(KUBECTL) logs -n $(AIRFLOW_NAMESPACE) deploy/$(HELM_RELEASE)-scheduler -c scheduler --tail=200 -f

.PHONY: shell
shell: ## Shell inside the scheduler container
	$(KUBECTL) exec -it -n $(AIRFLOW_NAMESPACE) deploy/$(HELM_RELEASE)-scheduler -c scheduler -- bash

.PHONY: uninstall
uninstall: ## Remove the Helm release (keeps the PostgreSQL PVC)
	helm uninstall $(HELM_RELEASE) -n $(AIRFLOW_NAMESPACE)

##@ Development
.PHONY: new-dag
new-dag: ## Scaffold a DAG: make new-dag NAME=my_dag [ARGS='-s "0 6 * * *"']
	@test -n "$(NAME)" || (echo "Usage: make new-dag NAME=<dag_id>"; exit 1)
	scripts/create_dag.sh $(NAME) $(ARGS)

.PHONY: check-dags
check-dags: ## Static sanity check of every DAG
	python3 tools/check_dags.py

.PHONY: lint
lint: ## ruff + yamllint + shellcheck
	ruff check .
	ruff format --check .
	yamllint .
	shellcheck -x scripts/*.sh scripts/lib/*.sh tests/*.sh k8s/cronjobs/scripts/*.sh

.PHONY: test
test: ## Unit tests + render test
	python3 -m pytest
	bash tests/test_render_config.sh

.PHONY: dev-install
dev-install: ## Install local dev tooling (venv recommended)
	python3 -m pip install -r requirements-dev.txt
	pre-commit install
