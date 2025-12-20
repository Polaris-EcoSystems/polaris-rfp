# Runbooks

These are the first-response playbooks for common production incidents.

## Quick triage checklist (always)

1. **Get a reference id**: ask the user for the “Ref” shown in the UI toast or on `/support`.
2. **Check CloudWatch dashboard**: `polaris-backend-<env>` (ALB 5xx, latency p95, ECS CPU/memory).
3. **Find correlated logs**:
   - Backend logs are JSON in CloudWatch Logs group: `/ecs/polaris-backend-<env>`
   - Filter by `request_id` / `requestId` equal to the user’s reference.
4. **Decide blast radius**: single user, single tenant, or systemic.
5. **Mitigate first**: reduce impact (feature flag / circuit breaker / rollback), then debug root cause.

## Runbooks

- [Auth & sessions](auth.md)
- [OpenAI / AI degradation](openai.md)
- [DynamoDB throttling / storage errors](dynamodb.md)
- [ALB 502/504, latency, ECS saturation](alb-ecs.md)
- [Stuck background jobs (RFP upload / AI jobs)](stuck-jobs.md)
