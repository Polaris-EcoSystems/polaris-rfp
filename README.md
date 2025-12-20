# Polaris RFP

Polaris is a production-oriented RFP intake and proposal generation system.

## Architecture (current)

- **Frontend**: Next.js (App Router) with a server-side BFF under `/api/**` that proxies to the backend and attaches auth.
- **Backend**: FastAPI (Python) running on ECS Fargate behind an ALB.
- **Auth**: AWS Cognito (custom challenge / magic-link) + server-side session refresh.
- **Data**: DynamoDB (primary persistence) + S3 (uploaded assets/source PDFs, headshots, etc.).
- **AI**: OpenAI API (model configurable per purpose).
- **Infra**: CloudFormation nested stacks under `.github/cloudformation/` (Amplify + ECS/ALB + Cognito + DynamoDB + S3).

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

## Repo layout

```text
backend/   # FastAPI app + services + DynamoDB repos
frontend/  # Next.js App Router UI + BFF route handlers
.github/   # CloudFormation templates and deployment workflow
```
