# OpsForge AI

Autonomous multi-agent platform for enterprise order-exception investigation and human-in-the-loop resolution.

OpsForge ingests operational exceptions (for example ERP vs vendor-portal status mismatch), runs a LangGraph agent pipeline, optionally pauses for human approval, updates an ERP-style system of record (mocked), generates an investigation report, and sends email notifications. A Next.js operations console supports simulate, review, approve/reject, and ERP data management. The full stack runs with Docker Compose. Backend quality is covered by pytest.

---

## Business problem

Operations teams spend significant time on repetitive exception handling across ERP, carrier/vendor portals, and email. Status mismatches, delays, and inventory issues need investigation, evidence collection, controlled system updates, and clear communication.

OpsForge automates investigation and recommendations while keeping humans in control for high-severity or policy-driven cases.

---

## What this project demonstrates

- Multi-agent orchestration with **LangGraph** (async flow, PostgreSQL checkpointer, human-in-the-loop interrupt)
- **FastAPI** backend with JWT auth and PostgreSQL
- **Kafka** event-driven intake (HTTP producer + background consumer)
- **Playwright** browser agent for vendor-portal style evidence
- **MuleSoft-style ERP mock** (PostgreSQL-backed integration layer)
- **Mailpit** for HITL and final notification emails
- **Next.js** operations console (dashboard, simulate, approvals, case detail, ERP orders)
- **Docker Compose** one-command local runtime
- **Pytest** backend tests with coverage gate

---

## Functional flow

```text
1. Operator feeds ERP orders (UI or API) into the mock system of record
2. Operator (or upstream system) submits an exception event
   - UI/API: POST /api/v1/events/simulate
   - Creates agent_executions row (status running/pending)
   - Publishes JSON event to Kafka topic
3. FastAPI lifespan keeps an asyncio Kafka consumer running
4. Consumer receives message → handle_exception_event
5. LangGraph agents run in order:
   - Planner      → investigation plan (LLM)
   - Research     → load order/exception context from PostgreSQL
   - Browser      → Playwright collects portal evidence
   - Integration  → decision rules (ERP vs portal); may prepare ERP update
   - Human review → interrupt when policy requires approval (waiting_human)
   - Reporting    → structured investigation report
   - Notification → email via SMTP (Mailpit)
6. If waiting_human:
   - HITL email is sent
   - Operator opens case in UI, reviews evidence, Approve or Reject
   - POST /api/v1/executions/{thread_id}/approve resumes the graph
   - Final report + final email; status completed (or failed)
7. If policy allows auto-complete:
   - Graph finishes without interrupt → completed + final email
```

**Status path (typical HITL case):**

```text
pending/running → waiting_human → (approve/reject) → completed
```

**Status path (auto path):**

```text
pending/running → completed
```

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

---

## Repository structure

```text
opsforge-ai/
├── app/                   # Backend: API, agents, Kafka, email, auth
├── tests/                 # Backend pytest suite
├── frontend/              # Next.js operations console
├── Dockerfile             # Backend image
├── frontend/Dockerfile    # Frontend image
├── docker-compose.yml
├── requirements.txt
├── .env.example
├── README.md
└── reports/               # Test/coverage output (local, gitignored)
```

---

## Quick start

### Prerequisites

- Docker Desktop
- LLM provider API key (e.g. OpenRouter)

### Configure environment

```bash
cp .env.example .env
```

Minimum:

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

### Start the stack

```bash
docker compose up -d --build
docker compose ps
```

| Service            | URL                          |
| ------------------ | ---------------------------- |
| Operations console | http://localhost:3000        |
| API docs (Swagger) | http://localhost:8000/docs   |
| API health         | http://localhost:8000/health |
| Mailpit UI         | http://localhost:8025        |

### Stop

```bash
docker compose down
```

Named volumes keep Postgres data unless you run `docker compose down -v`.

---

## Demo flow (interview)

1. Open http://localhost:3000 and sign in.
2. **ERP Orders** — feed sample orders if the list is empty.
3. **Simulate** — create an exception for a known `order_number`.
4. Open the execution case — confirm lifecycle and evidence (ERP + portal).
5. If status is `waiting_human` — **Approve** or **Reject** with notes.
6. Open http://localhost:8025 — confirm HITL and/or final emails.
7. Confirm final report and status `completed` on the case page.

---

## API overview (selected)

| Method | Path                                     | Purpose                                |
| ------ | ---------------------------------------- | -------------------------------------- |
| POST   | `/api/v1/auth/register`                  | Register user                          |
| POST   | `/api/v1/auth/token`                     | Login (OAuth2 password form)           |
| GET    | `/api/v1/me`                             | Current user                           |
| POST   | `/api/v1/events/simulate`                | Create execution + publish Kafka event |
| GET    | `/api/v1/executions`                     | List/filter executions                 |
| GET    | `/api/v1/executions/{thread_id}`         | Case detail                            |
| POST   | `/api/v1/executions/{thread_id}/approve` | Human decision / resume graph          |
| POST   | `/api/v1/erp/orders`                     | Feed ERP mock orders                   |
| GET    | `/api/v1/erp/orders`                     | List ERP orders                        |

Full interactive schema: http://localhost:8000/docs

---

## Event-driven processing

- **Producer:** `POST /api/v1/events/simulate` (or any publisher to the same Kafka topic with a compatible JSON payload).
- **Consumer:** started in FastAPI **lifespan** as an asyncio background task (no cron). Continuously polls the exceptions topic and invokes `handle_exception_event`.

---

## Testing (backend)

Stack must be running (or at least the `app` service with DB available).

### Run tests with coverage gate

```bash
docker compose exec app pytest tests/ -q --cov=app --cov-fail-under=80 --cov-report=term-missing --cov-report=html:reports/coverage --html=reports/test_report.html --self-contained-html
```

Shorter form:

```bash
docker compose exec app pytest -q --cov=app --cov-fail-under=80 --cov-report=html:reports/coverage --html=reports/test_report.html --self-contained-html
```

### Open reports (Windows, from project root)

```bash
start reports\test_report.html
start reports\coverage\index.html
```

macOS:

```bash
open reports/test_report.html
open reports/coverage/index.html
```

Linux:

```bash
xdg-open reports/test_report.html
xdg-open reports/coverage/index.html
```

Ensure `./reports` is mounted on the `app` service in `docker-compose.yml` so HTML reports appear on the host.

Frontend E2E automation is out of scope; UI is validated via the manual demo flow above.

---

## Observability (optional)

When `LANGCHAIN_TRACING_V2` and a valid LangSmith API key are set, agent-pipeline spans can be viewed in LangSmith. Prefer tracing the exception path (`handle_exception_event`, agent nodes, resume after approval), not high-frequency GET polling endpoints.

---

## Design notes

- **Human-in-the-loop:** policy (severity/confidence/mismatch rules) can interrupt before final ERP commit; operators approve or reject with notes.
- **ERP / MuleSoft:** integration is mocked on PostgreSQL to demonstrate update and audit patterns without live Anypoint credentials; code comments document a real connector path.
- **Email:** SMTP to Mailpit for local demos (approval-required alert and final outcome).
- **Browser evidence:** Playwright-based agent against a controlled mock portal for deterministic demos.

---

## Author

Full-stack portfolio system: autonomous multi-agent backend, operations UI, Dockerized runtime, and automated backend tests focused on a realistic exception-management business case.

```

```
