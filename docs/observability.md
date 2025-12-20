# Observability

## What’s in the repo today

- **Request correlation**: every backend response includes `X-Request-Id` and the frontend BFF forwards/returns `x-request-id` so support can correlate browser → BFF → backend.
- **CloudWatch dashboard + alarms (backend)**: the CloudFormation template adds a basic dashboard and alarms for:
  - ALB 5xx
  - Target 5xx
  - Target latency p95
  - ECS CPU + Memory

See: `.github/cloudformation/backend-ecs-alb.yml`.

## Enabling OpenTelemetry tracing (backend)

The backend supports optional OpenTelemetry tracing. It is **off by default**.

### Environment variables

- `OTEL_ENABLED=true`
- `OTEL_SERVICE_NAME=polaris-rfp-backend`
- `OTEL_EXPORTER_OTLP_ENDPOINT=http://<collector-host>:4318/v1/traces`

### Recommended production setup

Run an OTLP collector (e.g. AWS Distro for OpenTelemetry) in the same VPC, then set `OTEL_EXPORTER_OTLP_ENDPOINT` for the ECS task to point at it.

Notes:

- If `OTEL_ENABLED=true` but no exporter endpoint is configured, the backend falls back to a **console exporter** (useful for debugging; not recommended for production).
