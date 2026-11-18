# Hands-on Walkthrough: Build a Self-Service Developer Platform

This lab takes you from an empty machine to a working platform where a developer ships a service by writing one file. Every step has three parts:

- **Real life:** what this step means in a real company, in plain words
- **Do it:** the exact commands
- **Screenshot:** what to capture for your portfolio (file name goes in `docs/screenshots/`)

Plan for about two focused days. Don't rush the "Understand it" notes; they are what you'll explain in interviews.

---

## The story you are acting out

**KudiPay** (made up) is a fintech with 6 product squads and a 2-person platform team. Today, when the Payments squad builds a new service, they open tickets: one for a Nomad job, one for CI, one for a gateway route, and nobody remembers monitoring. It takes about a week, and the platform team is the bottleneck for every squad.

You are going to play **both roles**:

| Hat | You do | Files you touch |
| --- | --- | --- |
| Platform engineer | Build the "office tower" once: scheduler, registry, gateway, monitoring, templates, guardrails | `infra/`, `platform/`, `.github/workflows/service-pipeline.yml` |
| Developer (Payments squad) | Ship `invoice-api` without asking anyone | `services/invoice-api/` only |

### The one analogy to keep in your head

Think of the platform as a **serviced office tower**:

| Tower | Platform piece | Why |
| --- | --- | --- |
| Building manager who assigns office space | **Nomad** | Decides which machine runs each container, restarts it if it dies |
| The lobby directory that updates itself | **Consul** | Lists every service, where it is, and whether it's healthy |
| Reception and security desk | **APISIX** | Every visitor enters here; it checks, limits and directs them to the right floor |
| Smoke detectors and the control room | **Prometheus + Grafana + Alertmanager** | Measures everything, shows it on screens, calls the right person when something burns |
| The standard tenancy form | **`platform.yaml`** | Tenants fill one form; the building handles the rest |
| The building's standard move-in procedure | **GitHub Actions reusable workflow** | Every tenant moves in the same safe way |

---

## Phase 0 — Prepare your machine (≈1 hour)

**Real life:** a new engineer's laptop setup. Boring, but you only do it once.

You need **Linux**. On Windows, use **WSL2 with Ubuntu** and install Docker Engine *inside* Ubuntu (not Docker Desktop's WSL integration — the lab uses host networking, which needs a real Linux Docker daemon). A cheap Ubuntu VPS also works.

**WSL2 only** — turn on systemd so Docker can run as a service:

```bash
sudo tee /etc/wsl.conf >/dev/null <<'EOF'
[boot]
systemd=true
EOF
```

Then in Windows PowerShell: `wsl --shutdown`, and reopen Ubuntu. If Docker Desktop is installed, disable its integration for this distro (Docker Desktop → Settings → Resources → WSL integration).

**Do it:**

```bash
git clone https://github.com/YOUR_USERNAME/self-service-platform-lab.git   # or unzip the starter
cd self-service-platform-lab
bash scripts/install-tools.sh
newgrp docker          # or log out and back in
docker run --rm hello-world
```

**Expect:** versions of Docker, Docker Compose, Nomad and PyYAML printed at the end.

**Screenshot:** none yet. (Nobody hires for installing Docker.)

---

## Phase 1 — Platform team: open the building (≈30 min)

**Real life:** before any tenant moves in, the building needs power, a lobby directory, reception and smoke detectors. This is the platform team's one-time work.

**Do it:**

```bash
make up          # Consul, etcd, APISIX, Prometheus, Alertmanager, Grafana
```

Open a **second terminal** (keep it visible, the logs are educational):

```bash
make nomad       # Nomad agent in dev mode, asks for your sudo password
```

Back in the first terminal:

```bash
make urls
nomad node status          # one node, status "ready"
```

Open each UI in your browser: Nomad `http://localhost:4646`, Consul `http://localhost:8500`, Prometheus `http://localhost:9090/targets`, Grafana `http://localhost:3000` (admin / admin, skip the password change).

**Screenshot:**
- `01-platform-up.png` — terminal with `make up` output and the `docker compose ps` table showing all services running
- `02-nomad-ui-node.png` — Nomad UI → Clients, showing one ready node

**Understand it:**
- Everything runs on `network_mode: host`, so APISIX and Prometheus can reach containers that Nomad starts on `127.0.0.1`. In production these would be separate machines talking over a private network.
- Nomad runs in **dev mode**: a server and client in one process, data kept in memory. Restart it and jobs are gone. Fine for a lab, never for production.
- APISIX's built-in control API normally listens on port 9090, which clashes with Prometheus. Look in `infra/apisix/config.yaml` to see how it's moved to 9092. Small conflicts like this are real platform work.

---

## Phase 2 — Platform team: onboard the Payments squad (≈10 min)

**Real life:** a new tenant signs the lease. They get their own floor (a Nomad **namespace**) so their things never mix with another team's.

**Do it:**

```bash
cat platform/teams.yaml
make onboard TEAM=payments
nomad namespace list
```

Try onboarding a team that isn't in the file:

```bash
make onboard TEAM=marketing
```

**Expect:** `payments` appears in the namespace list; `marketing` is refused with "add it to platform/teams.yaml first".

**Understand it:** `teams.yaml` is the **single source of truth** for who a team is. In a real company the same list would also create the GitHub team, the Grafana folder and the Alertmanager receiver, so they never drift apart. Adding a team is a reviewed pull request to this file, not a chat message.

---

## Phase 3 — Developer: fill in the tenancy form (≈20 min)

**Real life:** you (now the Payments developer) don't know or care how Nomad works. You fill in a short form describing your service.

**Do it:**

```bash
cat services/invoice-api/platform.yaml
make test
make validate
```

Now break the rules on purpose. Edit `platform.yaml`: set `memory: 4096` and `team: ghosts`, then:

```bash
make validate
```

**Expect:** two clear errors: unknown team, and memory above the 1024 MB cap. Undo your edits and validate again.

**Screenshot:** `03-validate-guardrails.png` — the failing validation (red errors) and then the passing one, in one terminal.

**Understand it:** these are **guardrails**: the platform team's rules, enforced by code before anything ships. Self-service doesn't mean "anything goes"; it means "anything inside the safe lane goes without a ticket". Open `validate()` in `platform/platformctl.py` and read the rules.

---

## Phase 4 — Developer: ship it (≈30 min)

**Real life:** you hand your form to the building. The building manager (Nomad) finds you space, the directory (Consul) lists you, and nobody from the platform team is involved.

**Do it:**

```bash
make build                 # docker image invoice-api:v1
make render                # see the Nomad job you did NOT have to write
make deploy                # renders, validates, runs, and follows the rollout
make status
```

**Expect:** `make deploy` streams the deployment and ends with it **successful**, 2 healthy allocations. `make status` shows 2/2 instances passing in Consul.

Now look around the UIs:
- Nomad UI → Jobs → switch namespace to **payments** → `invoice-api`
- Consul UI → Services → `invoice-api` → both instances green, tags `team=payments`, `metrics`, `apisix`

**Screenshot:**
- `04-rendered-job.png` — split screen: `platform.yaml` (20 lines) next to the generated `build/invoice-api.nomad.hcl` (~90 lines). This single image explains the whole project.
- `05-deploy-terminal.png` — the end of `make deploy` showing the successful deployment
- `06-nomad-ui-job.png` — Nomad UI job page in the payments namespace with 2 running allocations
- `07-consul-ui-service.png` — Consul UI service page with healthy instances and the tags visible

**Understand it:**
- Open `platform/templates/service.nomad.hcl.tpl`. The platform team decided once: rolling updates one at a time, health-check gating, `auto_revert = true`, restart policy, and the standard Consul tags. Every service gets these for free.
- The **`service` block** is the most important part: it's what registers the containers in Consul, and everything in the next phases depends on it.
- Ports are **dynamic**. Nomad picks a free host port and maps it to 8080 inside the container. That's why nothing can hard-code addresses, and why discovery matters.

---

## Phase 5 — Developer: open the front door (≈20 min)

**Real life:** your office exists, but visitors can't find it. Reception (APISIX) needs to know "visitors asking for *invoice* go to the Payments floor". You don't phone reception; the form already says it.

**Do it:**

```bash
make expose
curl -i -H "Host: invoice.localtest.me" http://127.0.0.1:9080/
for i in 1 2 3 4 5 6; do curl -s -H "Host: invoice.localtest.me" http://127.0.0.1:9080/ ; echo; done
curl -s -H "Host: invoice.localtest.me" -H 'Content-Type: application/json' \
  -d '{"customer":"Ada Stores","amount":25000}' http://127.0.0.1:9080/invoices
```

Then open `http://invoice.localtest.me:9080` in your browser. (`*.localtest.me` is a public DNS name that always points to 127.0.0.1, handy for labs.)

**Expect:** JSON with `service`, `version` and `instance`. In the loop, `instance` alternates between two container IDs: APISIX is load-balancing across both replicas. The response headers include `X-Request-Id` and rate-limit headers.

Look at what was created:

```bash
curl -s -H 'X-API-KEY: platform-lab-admin-key' http://127.0.0.1:9180/apisix/admin/routes/invoice-api | jq .value
```

**Screenshot:**
- `08-expose-and-curl.png` — terminal: `make expose`, then the 6-request loop with alternating instances
- `09-browser-service.png` — the browser showing the JSON response at `invoice.localtest.me:9080`

**Understand it:**
- The route's upstream says `"discovery_type": "consul", "service_name": "invoice-api"`. There are **no IP addresses** in the gateway config. APISIX asks Consul every few seconds where the healthy instances are.
- `platformctl expose` refuses if another team's route already owns the same hostname. That's a guardrail against two teams fighting over a domain.
- In production you'd add TLS here: a wildcard certificate for `*.api.yourdomain.com`, renewed automatically by a scheduled job, because APISIX doesn't issue certificates by itself.

---

## Phase 6 — Rate limiting (≈10 min)

**Real life:** a client's buggy app retries in a tight loop and floods your service. Reception lets each visitor in only so many times per minute, so one bad client can't take the building down.

**Do it:**

```bash
make ratelimit
```

**Expect:** about 300 × `HTTP 200` and the rest `HTTP 429` (Too Many Requests). The limit is per client IP, set by `rate_limit` in `platform.yaml`.

**Screenshot:** `10-rate-limit.png` — the counts of 200s and 429s.

**Understand it:** the developer picked the number; the platform capped it (`max_rate_limit` in `teams.yaml`). The limit lives in the gateway, so the service code never had to implement it. Wait a minute before the next phase so your IP's counter resets.

---

## Phase 7 — See everything without setting anything up (≈40 min)

**Real life:** the smoke detectors were installed in every office before anyone moved in. A new tenant doesn't call anyone to get monitoring; it's simply there.

**Do it:**

```bash
make load        # leave running ~5 minutes in its own terminal
```

While it runs:

1. Prometheus → `http://localhost:9090/targets`. Find the **consul-services** job: two `invoice-api` targets, each labelled `service="invoice-api"` and `team="payments"`. You never configured them.
2. Prometheus → Graph, run: `sum by (instance) (rate(app_requests_total[1m]))`
3. Grafana → Dashboards → Platform → **Service Overview (golden path)**. Pick team `payments`, service `invoice-api`.

**Screenshot:**
- `11-prometheus-targets.png` — the targets page showing the auto-discovered invoice-api targets with their labels
- `12-grafana-dashboard.png` — the full dashboard with traffic flowing (this is your README hero image, make it look good: dark theme, last 15 minutes)

**Understand it:**
- `infra/prometheus/prometheus.yml` has **one** scrape job for all services: "scrape anything in Consul tagged `metrics`". The `relabel_configs` copy the Consul `team=` tag into a Prometheus label. That label is what makes alert routing possible later.
- The dashboard is **one shared template** with a `$service` dropdown, provisioned from Git (`infra/grafana/`). Ten services = still one dashboard. Teams can add their own on top.
- Look at the "Gateway responses by status code" panel: you'll see the 429s from Phase 6. Those come from APISIX, not the app.
- Read `test_metrics_exposed_with_route_template_labels` in `test_app.py`. Metric labels use the route template (`/invoices/<invoice_id>`), never the raw ID. One label per invoice ID would create millions of time series and crash Prometheus. This is called **cardinality**, and it's a classic interview question.

---

## Phase 8 — Incident drill: the Friday-night outage (≈30 min)

**Real life:** Friday, 11 pm. A database hiccup makes half of all invoice requests fail. In the old world nobody notices until Monday. On the platform, the alert reaches the **Payments** on-call, not the platform team, because the alert knows who owns the service.

**Do it:** keep `make load` running (restart it if it finished), then:

```bash
make break       # 50% of requests now fail on every instance
```

Watch, over 2–3 minutes:
1. Grafana: error rate turns red, the 500 line rises in "Requests / sec by status".
2. Prometheus → Alerts: `HighErrorRate` goes **pending**, then **firing**.
3. Alertmanager → `http://localhost:9093`: the alert is grouped under receiver **payments-oncall**, with labels `team="payments"`, `service="invoice-api"`.

Then resolve the incident:

```bash
make fix
```

**Screenshot:**
- `13-alert-firing.png` — Alertmanager (or Prometheus Alerts) showing `HighErrorRate` firing with `team="payments"`
- `14-grafana-incident.png` — the dashboard showing the error spike and the recovery after `make fix`

**Understand it:**
- `scripts/chaos.sh` finds every instance **through Consul** and flips a chaos switch in each. Even your drill tools use the registry.
- The alert rule in `infra/prometheus/rules/baseline.yml` is generic: it doesn't mention invoice-api. Every service on the platform gets it automatically.
- `infra/alertmanager/alertmanager.yml` routes `team="payments"` to `payments-oncall`. To get real Slack messages, add a `slack_configs` block with a webhook URL (instructions in the file). A screenshot of a real Slack alert is a strong portfolio piece.

---

## Phase 9 — Safe deploys: rolling update and automatic rollback (≈30 min)

**Real life:** two releases. First a normal upgrade that customers never notice. Then a bad release, the kind that usually ruins a weekend, which the platform catches and undoes by itself.

**Part A — normal upgrade (v1 → v2):**

```bash
make build VERSION=v2
make deploy VERSION=v2
for i in 1 2 3 4; do curl -s -H "Host: invoice.localtest.me" http://127.0.0.1:9080/; echo; done
```

**Expect:** Nomad replaces instances one at a time, waiting for each to pass health checks. Responses now say `"version": "v2"`. With `make load` running, there's no error spike in Grafana.

**Part B — a broken release:**

```bash
make bad-release      # image whose /healthz returns 500
```

**Expect (≈1–2 minutes):** Nomad starts one new instance, its health check never passes, the deployment is marked **failed**, and Nomad **automatically reverts** to the last good version (v2). The other instance kept serving traffic the whole time.

Check it: Nomad UI → `invoice-api` → **Versions** and **Deployments** tabs. You'll see the bad version and the reverted one.

**Screenshot:** `15-bad-release-revert.png` — Nomad UI Deployments/Versions showing the failed deployment and the automatic revert (or the terminal with the failure message next to it).

**Understand it:**
- This comes from three lines in the template: `health_check = "checks"`, `healthy_deadline = "1m"`, `auto_revert = true`. The developer got it without knowing it exists.
- Verify for yourself whether APISIX sent any traffic to the unhealthy instance: run the curl loop during the bad release and look for errors. Write down what you observed; "I verified it" is better than "the docs say so".

---

## Phase 10 — The self-service "aha" moment: scale up (≈15 min)

**Real life:** Black Friday is coming. Payments needs a third instance. Old world: a ticket. Platform world: change one number.

**Do it:** edit `services/invoice-api/platform.yaml`, set `replicas: 3`, then:

```bash
make deploy VERSION=v2
make status
```

With `make load` running, watch Grafana's **"Requests per instance"** panel: a third line appears within about a minute.

**Expect:** 3/3 healthy in Consul, APISIX spreads traffic across all three, Prometheus scrapes all three. **You did not touch the gateway or monitoring config.**

**Screenshot:** `16-scale-to-3.png` — Grafana "Requests per instance" with three lines (optionally with the one-line `platform.yaml` diff beside it).

**Understand it:** this one change proves the whole design: Nomad registers the new instance in Consul, and APISIX and Prometheus both discover it from there. That's the sentence to say in an interview.

---

## Phase 11 — CI/CD with GitHub Actions (≈1–2 hours)

**Real life:** the standard move-in procedure. Every tenant moves in the same safe way, and when head office improves the procedure, every tenant benefits.

### 11.1 Push the repo

```bash
git init && git add . && git commit -m "Self-service platform lab"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/self-service-platform-lab.git
git push -u origin main
```

Replace `YOUR_USERNAME` in `README.md` (badge) too.

**Expect:** GitHub → **Actions** → `ship-invoice-api` runs: Validate → Unit tests → Build, scan and push + Smoke test.

**Screenshot:** `17-github-actions-run.png` — the run's job graph, all green. Click into "Smoke test on ephemeral Nomad + Consul" so the steps are visible.

**Understand it:**
- `ship-invoice-api.yml` is 15 lines; it calls `service-pipeline.yml` with `uses:`. That's a **reusable workflow**: the platform team owns the logic once.
- The **smoke test** starts a throwaway Consul + Nomad inside the GitHub runner, deploys with the exact same `platformctl deploy` developers use, and checks every instance is healthy. Your deploy tooling is tested on every change.
- Images are tagged with the commit SHA, never `latest`, so every deploy is traceable and roll-back-able.
- Trivy fails the build on fixable critical vulnerabilities.

### 11.2 Find your image

GitHub → your profile → **Packages** → `invoice-api`. Open package settings and set visibility to **Public** (needed if your lab will pull it in 11.4).

**Screenshot:** `18-ghcr-package.png` — the package page showing the SHA-tagged image.

### 11.3 Guardrails in a pull request

```bash
git checkout -b try-big-memory
sed -i 's/memory: 128/memory: 4096/' services/invoice-api/platform.yaml
git commit -am "Ask for 4 GB memory" && git push -u origin try-big-memory
```

Open a pull request on GitHub.

**Expect:** the **Validate platform.yaml** check fails with "memory 4096 exceeds cap 1024 MB".

**Screenshot:** `19-pr-guardrail.png` — the PR page with the failed check and the error message expanded.

Close the PR without merging. To make this a hard block, add a branch protection rule (or ruleset) on `main` that requires the `ship` checks to pass.

### 11.4 Optional: real deploys from GitHub to your lab

**Real life:** GitHub can't reach your laptop's Nomad. Companies solve this with a **self-hosted runner** inside their network. You'll do the same.

> **Security:** never leave a self-hosted runner attached to a public repo, because anyone could open a pull request that runs code on your machine. Keep the repo private while the runner is connected, or only run it during your demo.

1. GitHub → repo **Settings → Actions → Runners → New self-hosted runner** → Linux. Run the shown commands in your WSL/Ubuntu terminal. When `config.sh` asks for labels, enter `platform-lab`. Then `./run.sh`.
2. **Settings → Environments** → create `lab` (optionally add yourself as a required reviewer, that gives you an approval button).
3. **Settings → Secrets and variables → Actions → Variables** → add `ENABLE_LAB_DEPLOY` = `true`.
4. Push any change to `services/invoice-api/`.

**Expect:** after the smoke test, a **Deploy to lab** job runs on your machine, deploys the GHCR image to your Nomad and exposes it. `curl` now shows the commit SHA as the version.

**Screenshot:** `20-self-hosted-deploy.png` — the Actions run with the deploy job green, plus the curl output showing the SHA version.

---

## Phase 12 — Turn it into portfolio material (≈1–2 hours)

1. **Screenshots:** save them in `docs/screenshots/` with the exact names in the checklist below. The README already references them.
2. **Hero image:** use `12-grafana-dashboard.png` at the top of the README.
3. **Pin the repo** on your GitHub profile and add topics: `platform-engineering`, `nomad`, `consul`, `apisix`, `prometheus`, `grafana`, `github-actions`, `devops`.
4. **Short demo video (2–3 min):** screen-record Phase 10 (scale to 3) and Phase 8 (alert firing). Video is what recruiters actually watch.
5. **Resume bullets** (adjust to what you actually did):
   - Built a self-service developer platform on Nomad, Consul, APISIX and Prometheus/Grafana where a 20-line service descriptor replaces hand-written scheduler, gateway and monitoring config.
   - Designed a reusable GitHub Actions pipeline with descriptor validation, Trivy scanning and smoke tests on an ephemeral Nomad cluster.
   - Implemented Consul-based service discovery so the gateway and monitoring pick up new or scaled services with no manual changes; added team-based alert routing and automatic rollback of failed releases.

### Interview questions this project prepares you for

| Question | Your answer comes from |
| --- | --- |
| "What is a golden path / internal developer platform?" | The story at the top + Phase 3 |
| "How does service discovery work, and why not hard-code IPs?" | Phase 4–5, dynamic ports + Consul |
| "How do you stop one team from hurting others on a shared platform?" | Namespaces, guardrails, rate limits, route ownership |
| "How do you roll back a bad deploy?" | Phase 9, health-gated rolling updates + auto-revert |
| "What is label cardinality?" | Phase 7, route-template labels |
| "How do alerts reach the right team?" | Phase 7–8, Consul tag → Prometheus label → Alertmanager route |
| "How do you keep 20 repos' pipelines consistent?" | Phase 11, reusable workflows with versioning |
| "What would you change for production?" | README "What I'd add for production" |

---

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `docker compose` services keep restarting | Port already in use | `sudo ss -ltnp \| grep -E '8500\|9080\|9090\|3000'`, stop the other program |
| `nomad job run` never becomes healthy | Consul can't reach the container | `make status`; check Consul UI check output; make sure Docker Engine runs inside WSL, not Docker Desktop |
| `make expose` "cannot reach http://127.0.0.1:9180" | APISIX not up yet or etcd down | `docker compose -f infra/docker-compose.yml logs apisix etcd` |
| Gateway returns 503 | No healthy instances in Consul | `make status`; redeploy |
| Browser on Windows can't open `localhost:4646` | WSL localhost forwarding | Add `networkingMode=mirrored` under `[wsl2]` in `%UserProfile%\.wslconfig`, then `wsl --shutdown` |
| Grafana panels empty | No traffic yet, or wrong service selected | Run `make load`, set the time range to "Last 15 minutes" |
| Nomad memory/CPU panels empty | Metric or label names differ in your Nomad version | In Prometheus, search `nomad_client_allocs` and adjust the query in the dashboard JSON |
| Everything vanished after a reboot | Nomad dev mode keeps state in memory | `make nomad`, then `make deploy` and `make expose` again |
| Image versions not found | Tag removed upstream | Bump the tags in `infra/docker-compose.yml` to current releases |

Reset everything: `make clean && make down`, stop Nomad with Ctrl+C.

---

## Screenshot checklist

| # | File name | What it shows | Phase |
| --- | --- | --- | --- |
| 1 | `01-platform-up.png` | `make up` + all platform containers running | 1 |
| 2 | `02-nomad-ui-node.png` | Nomad UI, one ready client node | 1 |
| 3 | `03-validate-guardrails.png` | Failing then passing `make validate` | 3 |
| 4 | `04-rendered-job.png` | `platform.yaml` beside the generated Nomad job | 4 |
| 5 | `05-deploy-terminal.png` | Successful `make deploy` | 4 |
| 6 | `06-nomad-ui-job.png` | Job in `payments` namespace, 2 allocations | 4 |
| 7 | `07-consul-ui-service.png` | Healthy instances with `team=payments` tags | 4 |
| 8 | `08-expose-and-curl.png` | Route created, requests alternating instances | 5 |
| 9 | `09-browser-service.png` | Service JSON in the browser | 5 |
| 10 | `10-rate-limit.png` | 200 vs 429 counts | 6 |
| 11 | `11-prometheus-targets.png` | Auto-discovered targets with labels | 7 |
| 12 | `12-grafana-dashboard.png` | Shared dashboard under load (hero image) | 7 |
| 13 | `13-alert-firing.png` | `HighErrorRate` firing, routed to payments-oncall | 8 |
| 14 | `14-grafana-incident.png` | Error spike and recovery | 8 |
| 15 | `15-bad-release-revert.png` | Failed deployment auto-reverted | 9 |
| 16 | `16-scale-to-3.png` | Three instances receiving traffic | 10 |
| 17 | `17-github-actions-run.png` | Reusable pipeline run, all green | 11 |
| 18 | `18-ghcr-package.png` | SHA-tagged image in GHCR | 11 |
| 19 | `19-pr-guardrail.png` | PR blocked by memory cap | 11 |
| 20 | `20-self-hosted-deploy.png` | Deploy job on self-hosted runner (optional) | 11 |

**Tips for good screenshots:** use dark theme everywhere, zoom the browser to 110–125%, crop to the useful area, and make sure no real secrets or personal tokens are visible.
