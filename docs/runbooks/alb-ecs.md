# ALB 502/504, latency, ECS saturation

## Symptoms

- Users see 502/504 errors
- The app feels “slow”
- Spiky failure rates during peak usage

## Checks

1. **CloudWatch dashboard**: `polaris-backend-<env>`
   - ALB 5xx
   - Target 5xx
   - TargetResponseTime p95
   - ECS CPU/Memory
2. **Backend logs**:
   - Look for timeouts, unhandled exceptions, or dependency failures (Cognito/OpenAI/DynamoDB).

## Mitigations

- If ECS CPU/memory is high:
  - Increase `DesiredCount`, `Cpu`, and/or `Memory` in the backend stack.
- If latency p95 is high:
  - Defer heavy work to background jobs (avoid long synchronous requests).
  - Reduce frontend polling frequency and add caching where safe.
- If Target 5xx is high:
  - Roll back the last deployment if correlated with a release.
  - Inspect top failing routes by request logs.

## Follow-ups (hardening)

- Add more alarms:
  - TargetResponseTime p99 for AI-heavy endpoints
  - Alarm on 4xx spikes (potential abuse)
- Add autoscaling policies (CPU and/or ALB request count).
