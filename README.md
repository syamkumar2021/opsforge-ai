# OpsForge AI

Autonomous multi-agent platform for enterprise order-exception investigation and human-in-the-loop resolution.

OpsForge ingests operational exceptions (for example ERP vs vendor-portal status mismatch), runs a LangGraph agent pipeline, optionally pauses for human approval, updates an ERP-style system of record (mocked), generates an investigation report, and sends email notifications. A Next.js operations console supports simulate, review, approve/reject, and ERP data management. The full stack runs with Docker Compose. Backend quality is covered by pytest. GitHub Actions CI publishes container images to GHCR for CD.

---

## Business problem

Operations teams spend significant time on repetitive exception handling across ERP, carrier/vendor portals, and email. Status mismatches, delays, and inventory issues need investigation, evidence collection, controlled system updates, and clear communication.

OpsForge automates investigation and recommendations while keeping humans in control for high-severity or policy-driven cases.

---

## What this project demonstrates

- Multi-agent orchestration with **LangGraph** (async flow, PostgreSQL checkpointer, human-in-the-loop interrupt)
- **FastAPI** backend with JWT auth (OAuth2 password flow) and PostgreSQL
- **Kafka** event-driven intake (HTTP producer + background consumer)
- **Playwright** browser agent for vendor-portal style evidence
- **MuleSoft-style ERP mock** (PostgreSQL-backed integration layer)
- **Mailpit** for HITL and final notification emails
- **Next.js** operations console to demonstrate the backend (dashboard, simulate, approvals, case detail, ERP orders)
- **Docker Compose** one-command local runtime
- **Pytest** backend tests with coverage gate
- **GitHub Actions CI** that tests, builds, and publishes images to GHCR

---

## Functional flow

```text
1. Operator feeds ERP orders (UI or API) into the mock system of record
2. Operator submits an exception event from UI or API
   - POST /api/v1/events/simulate
   - Creates agent_executions row
   - Publishes JSON event to Kafka
3. FastAPI lifespan keeps an asyncio Kafka consumer running
4. Consumer receives message → handle_exception_event
5. LangGraph agents run in order:
   - Planner      → investigation plan (LLM)
   - Research     → load order context from PostgreSQL
   - Browser      → Playwright collects portal evidence
   - Integration  → decision rules (ERP vs portal)
   - Human review → interrupt when policy requires approval
   - Reporting    → investigation report
   - Notification → email via SMTP (Mailpit)
6. If waiting_human:
   - HITL email is sent first
   - Operator Approve or Reject
   - POST /api/v1/executions/{thread_id}/approve
   - Final report + final email → completed
7. If policy allows auto-complete:
   - Graph finishes without interrupt → completed + final email only
```

HITL path: `pending/running → waiting_human → (approve/reject) → completed`  
Auto path: `pending/running → completed`

---

## Architecture (high level)

```text
Next.js UI (localhost:3000)
    → FastAPI (localhost:8000)
        → Kafka topic
            → Consumer (lifespan background task)
                → LangGraph multi-agent graph
                    → PostgreSQL (orders, executions, checkpoints)
                    → Playwright evidence
                    → ERP mock update
                    → Mailpit emails
```

---

## Tech stack

| Layer         | Technology                                      |
| ------------- | ----------------------------------------------- |
| Frontend      | Next.js, TypeScript, Tailwind CSS               |
| Backend       | FastAPI, SQLAlchemy (async), Pydantic           |
| Agents        | LangGraph, LangChain, OpenAI-compatible LLM API |
| Data          | PostgreSQL                                      |
| Messaging     | Apache Kafka (KRaft)                            |
| Browser agent | Playwright (Python)                             |
| Email         | aiosmtplib → Mailpit                            |
| Runtime       | Docker Compose                                  |
| Tests         | pytest, pytest-asyncio, pytest-cov, pytest-html |
| CI            | GitHub Actions → GHCR images                    |

---

## Repository structure

```text
opsforge-ai/
├── app/
├── tests/
├── frontend/
├── data/
│   ├── sample_erp_orders.json
│   └── sample_exception_events.json
├── .github/workflows/ci.yml
├── Dockerfile
├── frontend/Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
├── README.md
└── reports/
```

---

## Quick start

### Prerequisites

- Docker Desktop
- LLM provider API key (for example OpenRouter)

### Configure environment

```bash
cp .env.example .env
```

Minimum `.env`:

```env
OPENAI_API_KEY=sk-or-v1-...
OPENAI_MODEL=meta-llama/llama-3.3-70b-instruct
OPENAI_BASE_URL=https://openrouter.ai/api/v1
SECRET_KEY=change-me-in-production
```

Optional LangSmith:

```env
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=lsv2_...
LANGCHAIN_PROJECT=opsforge-ai
```

### Start / stop

```bash
docker compose up -d --build
docker compose ps
docker compose down
```

| Service            | URL                          |
| ------------------ | ---------------------------- |
| Operations console | http://localhost:3000        |
| API docs (Swagger) | http://localhost:8000/docs   |
| API health         | http://localhost:8000/health |
| Mailpit UI         | http://localhost:8025        |

Named volumes keep Postgres data unless you run `docker compose down -v`.

---

## Demo login (authentication)

Auth uses **OAuth2 password flow** and issues a **JWT**. Protected APIs need:

```text
Authorization: Bearer <access_token>
```

### Default local admin

Created on first startup if no users exist.

| Field    | Value               |
| -------- | ------------------- |
| Email    | `admin@opsforge.ai` |
| Password | `OpsForge@123`      |
| Role     | Superuser           |

UI login: http://localhost:3000/login

Register:

```text
POST /api/v1/auth/register
```

```json
{
  "email": "personb@opsforge.ai",
  "password": "OpsForge@123",
  "full_name": "Person B"
}
```

Emails should use `@opsforge.ai`.

Get token:

```text
POST /api/v1/auth/token
Content-Type: application/x-www-form-urlencoded

username=admin@opsforge.ai
password=OpsForge@123
```

Current user: `GET /api/v1/me`

These credentials are for local demo only.

---

## Sample data files

| File | Purpose |
| ---- | ------- |
| `data/sample_erp_orders.json` | 10 mock ERP orders (`ORD-10001` to `ORD-10010`) |
| `data/sample_exception_events.json` | Ready-to-paste exception events, expected HTTP codes, HITL vs auto notes, approve/reject bodies |

---

## Feed ERP data first

Simulate needs orders in the mock ERP database.

**Endpoint:**

```text
POST /api/v1/erp/orders
Authorization: Bearer <token>
Content-Type: application/json
```

```bash
curl -X POST "http://localhost:8000/api/v1/erp/orders" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  --data-binary @data/sample_erp_orders.json
```

Confirm: `GET /api/v1/erp/orders`

You can also feed orders from the UI **ERP Orders** page.

---

## How to test exception events

**UI:** Simulate page → paste one `payload` from `data/sample_exception_events.json`  
**API:**

```text
POST /api/v1/events/simulate
Authorization: Bearer <token>
```

Approve / reject HITL cases:

```text
POST /api/v1/executions/{thread_id}/approve
```

Approve body:

```json
{
  "decision": "approved",
  "notes": "Vendor evidence verified. Proceed with ERP reconciliation."
}
```

Reject body:

```json
{
  "decision": "rejected",
  "notes": "Evidence insufficient. Keep ERP status unchanged."
}
```

Suggested order:

1. Validation events first (invalid type, invalid severity, missing fields, empty order number, no token)
2. Feed ERP 10 orders
3. Run `ORD-10001` high mismatch → waiting_human → approve
4. Replay same payload → expect `409` duplicate
5. Run low-severity `ORD-10003`
6. Run high/critical `ORD-10004` and `ORD-10005`
7. Run unknown order `ORD-99999`
8. Reset active executions if you need to reuse the same order numbers

---

## Input event validations

Checked on `POST /api/v1/events/simulate` **before** Kafka.

| Check | Result |
| ----- | ------ |
| No JWT | `401` |
| Missing `order_number`, `exception_type`, or `description` | `422` |
| Empty `order_number` | `422` |
| Empty / too-short `description` | `422` |
| `exception_type` not in allowed enum | `422` |
| `severity` not in `low`, `medium`, `high`, `critical` | `422` |
| Same `order_number` already `pending`, `running`, or `waiting_human` | `409` |
| Valid body | `200` and event is published |

Allowed `exception_type` values:

```text
inventory_shortage
payment_failure
shipping_delay
vendor_status_mismatch
address_issue
other
```

Unknown `order_number` is **accepted** (`200`). Research then reports “order not found”. That is not a 404 at simulate time.

---

## Portal evidence and scoring

Browser/portal mock status is derived from the **last digit of `order_number`**:

| Order ends with | Typical portal status |
| --------------- | --------------------- |
| 1 | In Transit |
| 2 | Out for Delivery |
| 3 | Delivered |
| 4 | Exception – Address Issue |
| 0, 5, 6, 7, 8, 9 | Label Created |

ERP status comes from the fed order (`processing`, `confirmed`, `shipped`, `delivered`).

**Confidence** is not the same for every case. Decision rules combine:

- browser collection success
- ERP found vs not found
- ERP status vs portal status
- `exception_type`
- `severity`

Better aligned evidence raises confidence. Missing ERP order, failed browser collection, or unclear mismatch lowers it.

---

## When human approval is required vs skipped

Human approval is a **policy decision** after research + browser + integration rules.

Usually goes to `waiting_human`:

- `severity` is `high` or `critical`
- confidence is below the policy threshold (commonly under about `0.75`)
- ERP order is missing, so the system cannot safely update the system of record
- clear mismatch plus high operational risk (`vendor_status_mismatch`, `address_issue`, `inventory_shortage`)

Often completes without HITL:

- `severity` is `low` (and sometimes `medium`)
- evidence is usable
- policy does not mark `requires_human`

`ORD-10003` + low severity is the usual auto-complete demo.

---

## Email timing

Emails go through Mailpit: http://localhost:8025

| Path | Emails |
| ---- | ------ |
| HITL case | Before approval: waiting-human alert. After approve/reject: final outcome email |
| Auto-complete case | Final email only |

The UI email card shows delivery status, recipients, subject, and sent time. Full bodies are in Mailpit.

---

## Sample exception events (summary)

Full JSON payloads: `data/sample_exception_events.json`

| # | Order | What it tests | Expected |
| - | ----- | ------------- | -------- |
| 1 | ORD-10001 | High vendor mismatch | `200` → HITL → approve → completed |
| 2 | ORD-10002 | Shipping delay | `200`, delay context in report |
| 3 | ORD-10003 | Low severity / Delivered portal | `200`, often no HITL |
| 4 | ORD-10004 | Address issue high | `200` → HITL |
| 5 | ORD-10005 | Inventory critical | `200` → HITL |
| 6 | ORD-10006 | Order exists, no extra exception row | `200`, investigation continues |
| 7 | ORD-10010 | Payment failure | `200`, payment context in report |
| 8 | ORD-10001 again | Duplicate active case | `409` |
| 9 | ORD-99999 | Unknown ERP order | `200`, order not found, usually HITL |
| 10 | — | Bad `exception_type` | `422` |
| 11 | — | Bad `severity` | `422` |
| 12 | — | Missing fields | `422` |
| 13 | — | Empty `order_number` | `422` |
| 14 | — | Empty description | `422` if min-length enabled |
| 15 | — | No auth token | `401` |

---

## Demo flow (interview)

1. Open http://localhost:3000 and sign in with `admin@opsforge.ai` / `OpsForge@123`.
2. Feed `data/sample_erp_orders.json` on **ERP Orders** or `POST /api/v1/erp/orders`.
3. Simulate `ORD-10001` from `data/sample_exception_events.json`.
4. Open the case. Confirm lifecycle, ERP research, and portal evidence.
5. If `waiting_human`, approve or reject with notes.
6. Check Mailpit http://localhost:8025 for HITL and/or final email.
7. Confirm status `completed` and the final report.

---

## API overview

| Method | Path | Purpose |
| ------ | ---- | ------- |
| POST | `/api/v1/auth/register` | Register user |
| POST | `/api/v1/auth/token` | Login and get JWT |
| GET | `/api/v1/me` | Current user |
| POST | `/api/v1/events/simulate` | Create execution + publish Kafka event |
| GET | `/api/v1/executions` | List/filter executions |
| GET | `/api/v1/executions/{thread_id}` | Case detail |
| POST | `/api/v1/executions/{thread_id}/approve` | Human decision / resume graph |
| POST | `/api/v1/erp/orders` | Feed ERP mock orders |
| GET | `/api/v1/erp/orders` | List ERP orders |

Full schema: http://localhost:8000/docs

---

## Testing (backend)

```bash
docker compose exec app pytest tests/ -q --cov=app --cov-fail-under=80 --cov-report=term-missing --cov-report=html:reports/coverage --html=reports/test_report.html --self-contained-html
```

Windows:

```bash
start reports\test_report.html
start reports\coverage\index.html
```

Ensure `./reports` is mounted on the `app` service.

---

## CI (GitHub Actions)

Workflow: `.github/workflows/ci.yml`

On PR and push to `main`: unit tests + image builds.  
On push to `main` only: publish to GHCR.

```text
ghcr.io/syamkumar2021/opsforge-ai:latest
ghcr.io/syamkumar2021/opsforge-ai:<git-sha7>
ghcr.io/syamkumar2021/opsforge-frontend:latest
ghcr.io/syamkumar2021/opsforge-frontend:<git-sha7>
```

Check runs: https://github.com/syamkumar2021/opsforge-ai/actions  
Check packages: https://github.com/syamkumar2021?tab=packages

DevOps CD pulls both SHA-tagged images and runs them with Postgres, Kafka, and Mailpit. Prefer the SHA tag, not only `latest`.

---

## Design notes

- HITL is policy-driven, not hardcoded for every event.
- ERP / MuleSoft is mocked on PostgreSQL; comments document a real connector path.
- Browser evidence uses a controlled mock portal for deterministic demos.
- Email: HITL alert before approval; final email after completion on both HITL and auto paths.

---

## Scope and authorship

This repository is a **backend-first** portfolio project.

The goal was to design a production-shaped agentic system around a real operations problem: exception intake, multi-agent investigation, human approval, ERP-style update, audit, and notification. The product idea, business flow, agent responsibilities, APIs, Kafka path, decision rules, HITL policy, data model, and demo scenarios come from that design work, informed by prior **MuleSoft 4** integration experience (APIs, system-of-record updates, exception handling, environments).

I do not have paid production tenure on FastAPI / LangGraph / Kafka. To avoid a “toy script” layout I used an LLM as a **structuring and formatting aid** (folders, naming, boilerplate, review of production conventions) while I specified the behavior, wrote and iterated the core backend logic, and verified the flow end to end.

The **Next.js 16 + Tailwind CSS v4** dashboard is a presentation layer for that backend. I am not a frontend specialist. I used LLM help to build the console so reviewers can run the same flows visually instead of only through Swagger. Treat the frontend as a demo UI, not as a claim of frontend expertise.

**Interview focus:** backend architecture, agents, integration mock, HITL, Docker, tests, and CI images.

---

## Author

Syam Kumar Chimakurthi — backend / integration engineer. OpsForge AI is a return-to-work portfolio system: agentic backend, operations console for demonstration, Dockerized runtime, GitHub Actions image publish, sample ERP + exception fixtures, and automated backend tests.
