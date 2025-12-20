# Stuck background jobs (RFP upload / AI jobs)

## Symptoms

- RFP upload analysis spins forever
- AI section generation stays “running” or “queued”
- Users retry repeatedly, causing load

## Evidence to collect

- **Job id** (from UI or from the API response)
- **Reference ID** (`x-request-id`) from the failing request

## Checks

### AI jobs

- UI: `/support` → “Job lookup” → “Lookup AI job”
- API: `GET /api/ai/jobs/<jobId>`

Statuses:

- `queued`: created, not started yet
- `running`: actively generating
- `completed`: finished successfully
- `failed`: finished with error (`error` field)

### RFP upload jobs

- UI: `/support` → “Lookup RFP upload job”
- API: `GET /api/rfp/upload/jobs/<jobId>`

## Mitigations

- If the job is stuck in `running` with no progress:
  - Ask the user to retry later; if repeatable, capture the RFP/proposal id and investigate in backend logs.
- If the job is stuck in `queued`:
  - Indicates background execution isn’t happening (task restarts, deploy churn). Consider temporarily scaling up or redeploying.

## Follow-ups (hardening)

- Move job execution to a durable queue/worker (SQS + ECS worker or Lambda).
- Add a “job watchdog” that marks jobs as failed after a timeout window and surfaces a user-friendly message.
