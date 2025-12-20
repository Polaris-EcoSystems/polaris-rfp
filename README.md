# Polaris RFP

Polaris is a production-oriented RFP intake and proposal generation system.

## Architecture

### Overview

Polaris is built on a microservices-style architecture using ECS Fargate, with three main runtime components:

1. **Backend API Service** (`polaris-backend-production`) - FastAPI HTTP API serving user requests
2. **Contracting Worker Service** (`polaris-contracting-worker-production`) - SQS queue processor for document generation
3. **NorthStar Job Runner** (`northstar-job-runner-production`) - Scheduled task executor for agent jobs and automation

All three share the same Docker image and codebase but run different entry points with different execution patterns.

### Component Details

#### 1. Backend API Service

**Purpose:** Serves HTTP API requests via Application Load Balancer (ALB)

**Deployment:** ECS Service (always running, `DesiredCount: 2`)

**Resources:** 1 vCPU, 2 GB memory

**Entry Point:** FastAPI (`uvicorn`) - default container command

**Architecture:**

- Internet-facing ALB → ECS Service (private subnets)
- Health-checked by ALB
- Handles synchronous API endpoints
- Some background tasks run inline via FastAPI BackgroundTasks

**Key Responsibilities:**

- User authentication (Cognito JWT validation)
- CRUD operations (RFPs, proposals, companies, etc.)
- AI content generation (some workloads run synchronously)
- Slack integration endpoints

#### 2. Contracting Worker Service

**Purpose:** Processes long-running contracting jobs (contract generation, budget workbooks, zip packaging)

**Deployment:** ECS Service (always running, `DesiredCount: 1`)

**Resources:** 0.5 vCPU, 1 GB memory

**Entry Point:** `python -m app.workers.contracting_worker`

**Architecture:**

- Polls SQS queue (`polaris-contracting-jobs-{env}`) continuously
- Long-running loop: receive message → process job → delete message
- Uses DynamoDB for job state tracking and idempotency

**Job Types:**

- `contract_generate` - Renders DOCX contracts from templates
- `budget_generate` - Generates Excel budget workbooks
- `package_zip` - Creates zip bundles of contracting files

**Key Characteristics:**

- Job queue pattern (SQS with DLQ)
- Idempotent job processing
- Retry logic with visibility timeout
- Progress tracking in DynamoDB

#### 3. NorthStar Job Runner

**Purpose:** Executes scheduled "agent jobs" for automation, maintenance, and AI agent workloads

**Deployment:** ECS Task (triggered by EventBridge Scheduler every 15 minutes)

**Resources:** 1 vCPU, 2 GB memory

**Entry Point:** `python -m app.workers.agent_job_runner`

**Architecture:**

- EventBridge Scheduler → ECS RunTask (one-shot execution)
- Processes due jobs from DynamoDB (`agent_jobs` table)
- Runs to completion, then exits
- Prevents overlapping runs (skips if previous task still active)
- Reports summary to Slack channel before shutdown

**Job Types:**

- `opportunity_maintenance` / `perch_refresh` - Syncs RFP state from platform
- `agent_daily_digest` - Generates daily Slack reports
- `agent_perch_time` / `telemetry_self_improve` - Self-improvement tasks
- `slack_nudge` - Sends Slack notifications
- `opportunity_compact` / `memory_compact` - Compacts journal data
- `self_modify_*` - GitHub PR automation (open PR, check status, verify ECS rollout)
- **Future:** `ai_agent_ask`, `ai_agent_analyze` - AI agent workloads (sandboxed)

**Key Characteristics:**

- Scheduled execution (15-minute intervals)
- Prevents overlapping runs via FlexibleTimeWindow
- Stateless per run (processes jobs, reports, exits)
- Automatic Slack reporting before shutdown

### Shared Infrastructure

All three components share:

- **Same Docker Image:** All use identical backend codebase/image
- **Same IAM Roles:** Shared `TaskRole` and `TaskExecutionRole` with permissions for:
  - DynamoDB (full access to main table)
  - S3 (assets bucket read/write)
  - Secrets Manager (OpenAI, JWT, Slack credentials)
  - Cognito (user management)
- **Same Environment Variables:** Identical configuration (DDB table, S3 bucket, Cognito IDs, etc.)
- **Same Network:** All in private subnets, same security group (no public IP)
- **Same Logging:** All log to CloudWatch Logs (separate log groups per component)

### Data Flow

```
┌─────────────────────────────────────────────────────────┐
│                    User Requests                         │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
         ┌──────────────────────┐
         │   ALB (Port 443)     │
         └──────────┬───────────┘
                    │
                    ▼
    ┌───────────────────────────────┐
    │ polaris-backend-production    │  ← HTTP API Service
    │ (ECS Service, always running) │
    │ CPU: 1vCPU, Mem: 2GB         │
    └─────┬─────────────────────────┘
          │
          ├─────────────────┬──────────────────┐
          │                 │                  │
          ▼                 ▼                  ▼
    ┌─────────┐      ┌──────────────┐  ┌─────────────┐
    │DynamoDB │      │S3 / Secrets  │  │SQS Queue    │
    └────┬────┘      └──────────────┘  └──────┬──────┘
         │                                      │
         │                                      │
         ▼                                      ▼
┌─────────────────────────────────────────┐  ┌────────────────────────────┐
│  polaris-contracting-worker-production  │  │  EventBridge Scheduler     │
│  (ECS Service, always running)          │  │  (every 15 min, no overlap)│
│  CPU: 0.5vCPU, Mem: 1GB                │  └──────────────┬─────────────┘
└─────────────────────────────────────────┘                │
                                                           │
                                                           ▼
                                              ┌────────────────────────────┐
                                              │northstar-job-runner-prod   │
                                              │(ECS Task, on-demand)       │
                                              │CPU: 1vCPU, Mem: 2GB       │
                                              └──────────────┬─────────────┘
                                                             │
                                                             ▼
                                                        ┌─────────┐
                                                        │DynamoDB │
                                                        │(jobs)   │
                                                        └─────────┘
```

### Execution Patterns

**Request-Driven (Backend API):**

- User makes HTTP request → ALB routes to ECS service → FastAPI handles request → Response
- Some background tasks run inline via FastAPI BackgroundTasks (non-durable)
- Fast response times required for user-facing endpoints

**Queue-Driven (Contracting Worker):**

- Worker continuously polls SQS queue in long-running loop
- Receives message → Processes job → Updates DynamoDB → Deletes message
- Retries handled by SQS visibility timeout + DLQ
- Good for workloads that need guaranteed delivery and retry logic

**Schedule-Driven (NorthStar Job Runner):**

- EventBridge Scheduler triggers ECS RunTask every 15 minutes
- Task starts → Checks for due jobs in DynamoDB → Processes jobs → Reports to Slack → Exits
- Skips if previous task still running (prevents overlapping executions)
- Good for periodic maintenance, automation, and scheduled AI agent workloads

### Future Expansion

The architecture is designed to support:

1. **AI Agent Sandboxing:** Long-running AI agent tasks will run via `northstar-job-runner` instead of the main API process, providing:

   - Isolation from API requests (no OOM, no CPU starvation)
   - Durability across deployments/restarts
   - Independent scaling and resource allocation
   - Automatic Slack reporting
   - Jobs stored in DynamoDB with `dueAt` timestamps

2. **Additional Workers:** New worker patterns can follow existing patterns:

   - **SQS Worker:** Like `contracting-worker` - for queue-driven workloads
   - **Scheduled Task:** Like `northstar-job-runner` - for time-based automation
   - **On-Demand Task:** Triggered via API → ECS RunTask - for ad-hoc workloads

3. **Enhanced Scheduling:** EventBridge Scheduler can be extended with:
   - Multiple schedules for different job types
   - Conditional execution based on job queue depth
   - Dynamic scheduling based on workload

## Local development (golden path)

### Prerequisites

- **Node.js**: 20+
- **Python**: 3.11+
- **Docker**: for DynamoDB Local

### 1) Configure environment

Copy the example env file and set local overrides:

```bash
cp environment.example .env
```

Recommended local values (edit `.env`):

- `API_BASE_URL=http://localhost:8080`
- `NEXT_PUBLIC_API_BASE_URL=http://localhost:8080`
- `FRONTEND_BASE_URL=http://localhost:3000`
- `FRONTEND_URL=http://localhost:3000`
- `DDB_ENDPOINT=http://localhost:8000`
- `DDB_TABLE_NAME=polaris-rfp-local`

Notes:

- Most `/api/**` endpoints require Cognito bearer auth. For a fully working local UI sign-in flow, you need valid `COGNITO_USER_POOL_ID` and `COGNITO_CLIENT_ID` values (typically from a dev stack deployed via CloudFormation).

### 2) Start everything

Run a single command to start DynamoDB Local + backend + frontend:

```bash
./scripts/dev.sh
```

This will:

- Start DynamoDB Local via Docker Compose
- Create/upgrade the backend venv and run `uvicorn app.main:app --reload`
- Install frontend deps (if missing) and run `next dev`

## Manual development commands

### DynamoDB Local

```bash
docker compose up -d
```

Optional admin UI: `http://localhost:8001`

### Backend

```bash
python -m venv backend/.venv
source backend/.venv/bin/activate
pip install -r backend/requirements.txt
PORT=8080 uvicorn app.main:app --reload --app-dir backend
```

### Frontend

```bash
cd frontend
npm install
API_BASE_URL=http://localhost:8080 npm run dev
```

## Testing

- **Backend tests**: `cd backend && pytest`
- **Frontend tests**: `cd frontend && npm test`
- **Frontend lint**: `cd frontend && npm run lint`

## Git hooks (pre-commit / pre-push)

This repo includes a `.pre-commit-config.yaml` that mirrors the **non-deploy** CI checks:

- **pre-commit**: backend `ruff` (fast sanity checks)
- **pre-push**: backend `ruff + mypy + pytest`, frontend `lint + test + build`, and `cfn-lint`

Install once:

```bash
brew install pre-commit
# or: pipx install pre-commit
pre-commit install
pre-commit install --hook-type pre-push
```

Run manually (optional):

```bash
pre-commit run --all-files
pre-commit run --hook-stage pre-push --all-files
```

## Slack integration (commands + agent)

The backend exposes Slack endpoints under:

- `/api/integrations/slack/commands` (slash commands, including `/polaris ask …`)
- `/api/integrations/slack/events` (Events API, including `app_mention`)
- `/api/integrations/slack/interactions` (Block Kit button clicks, action confirmations)

### Required environment variables

- `SLACK_ENABLED=true`
- `SLACK_SIGNING_SECRET=...`
- `SLACK_BOT_TOKEN=...` (recommended `xoxb-...`)
- `SLACK_DEFAULT_CHANNEL=...` (optional; used by some notifications)
- `SLACK_RFP_MACHINE_CHANNEL=...` (optional; recommended: channel ID like `C…`/`G…`)

Optional:

- `SLACK_SECRET_ARN=...` (use AWS Secrets Manager instead of env vars)
- `SLACK_AGENT_ENABLED=true|false`
- `SLACK_AGENT_ACTIONS_ENABLED=true|false` (controls whether the agent may propose actions that require confirmation)

### Slack app scopes (recommended)

Minimum for `/polaris ask` + `@Polaris` Q&A:

- `commands`
- `chat:write`
- `app_mentions:read`

For `/polaris upload` (ingest latest PDFs from a channel):

- `files:read`
- `conversations.history` (public channels) and/or `groups:history` (private channels)

For task assignment DMs (optional):

- `users:read.email`
- `im:write`

## Infrastructure

### CloudFormation Stacks

Infrastructure is defined as nested CloudFormation stacks under `.github/cloudformation/`:

- **`root-nested.yml`** - Root stack orchestrating all nested stacks
- **`network-vpc.yml`** - VPC, subnets, security groups
- **`auth-cognito.yml`** - Cognito user pool, magic link authentication
- **`backend-ecs-alb.yml`** - ECS cluster, backend API service, contracting worker service, ALB
- **`northstar-agent.yml`** - Scheduled agent tasks (job runner, ambient tick, daily reports)
- **`frontend-amplify.yml`** - Next.js frontend via AWS Amplify

### Deployment

Deployment is automated via GitHub Actions (`.github/workflows/deploy.yml`):

- Builds Docker image and pushes to ECR
- Deploys CloudFormation stacks in sequence
- Supports multiple environments (development, staging, production)

## Repo layout

```text
backend/              # FastAPI app + services + DynamoDB repos
  app/
    workers/          # ECS worker entry points
      - contracting_worker.py
      - agent_job_runner.py
      - ambient_tick_worker.py
      - daily_report_worker.py
    services/         # Business logic services
    routers/          # FastAPI route handlers
frontend/            # Next.js App Router UI + BFF route handlers
.github/
  cloudformation/    # CloudFormation templates
  workflows/         # GitHub Actions CI/CD
docs/                # Documentation and runbooks
```
