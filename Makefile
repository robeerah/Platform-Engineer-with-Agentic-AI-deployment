SERVICE_DIR ?= services/invoice-api
SERVICE     ?= invoice-api
VERSION     ?= v1
IMAGE       ?= $(SERVICE):$(VERSION)
CTL         := python3 platform/platformctl.py

.PHONY: help up down nomad onboard validate build render deploy expose status \
        load ratelimit break fix bad-release scale-demo test urls clean

help: ## Show all commands
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

# ---------- platform team ----------
up: ## Start Consul, APISIX, Prometheus, Alertmanager, Grafana
	docker compose -f infra/docker-compose.yml up -d
	@docker compose -f infra/docker-compose.yml ps

down: ## Stop the shared platform services
	docker compose -f infra/docker-compose.yml down

nomad: ## Run Nomad in dev mode (keep this terminal open)
	sudo nomad agent -dev -bind=127.0.0.1 -config=infra/nomad/agent.hcl

onboard: ## Onboard a team: make onboard TEAM=payments
	$(CTL) onboard $(TEAM)

# ---------- developer self-service ----------
validate: ## Check platform.yaml against platform guardrails
	$(CTL) validate $(SERVICE_DIR)

test: ## Run the service's unit tests
	cd $(SERVICE_DIR) && python3 -m pytest -q

build: ## Build the service image: make build VERSION=v2
	docker build -t $(IMAGE) --build-arg APP_VERSION=$(VERSION) $(SERVICE_DIR)

render: ## Show the Nomad job the platform generates
	$(CTL) render $(SERVICE_DIR) --image $(IMAGE) && cat build/$(SERVICE).nomad.hcl

deploy: ## Deploy (or update) the service on Nomad
	$(CTL) deploy $(SERVICE_DIR) --image $(IMAGE)

expose: ## Publish the service through APISIX
	$(CTL) expose $(SERVICE_DIR)

status: ## Nomad + Consul + APISIX status for the service
	$(CTL) status $(SERVICE_DIR)

# ---------- drills ----------
load: ## Send steady traffic for 5 minutes
	bash scripts/load.sh

ratelimit: ## Burst 400 requests to watch 429s
	bash scripts/ratelimit-test.sh

break: ## Make 50% of requests fail on every instance
	bash scripts/chaos.sh $(SERVICE) 0.5

fix: ## Clear the injected failures
	bash scripts/chaos.sh $(SERVICE) 0

bad-release: ## Ship a release whose health check fails (watch auto-revert)
	docker build -t $(SERVICE):bad --build-arg APP_VERSION=bad --build-arg HEALTHY=false $(SERVICE_DIR)
	-$(CTL) deploy $(SERVICE_DIR) --image $(SERVICE):bad

urls: ## Print every UI you need
	@echo "Nomad UI       http://localhost:4646"
	@echo "Consul UI      http://localhost:8500"
	@echo "Service        http://invoice.localtest.me:9080"
	@echo "Prometheus     http://localhost:9090/targets"
	@echo "Alertmanager   http://localhost:9093"
	@echo "Grafana        http://localhost:3000  (admin / admin)"

clean: ## Stop the service and remove its route
	-nomad job stop -purge -namespace payments $(SERVICE)
	-curl -s -X DELETE -H 'X-API-KEY: platform-lab-admin-key' http://127.0.0.1:9180/apisix/admin/routes/$(SERVICE)
	rm -rf build
