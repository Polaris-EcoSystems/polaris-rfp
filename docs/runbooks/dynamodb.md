# DynamoDB throttling / storage errors

## Symptoms

- 503 responses with “Service Unavailable”
- Increased latency across many endpoints
- Errors mentioning `DdbThrottled`, `ProvisionedThroughputExceeded`, or `TransactionCanceled`

## Evidence to collect

- **Reference ID** (`x-request-id`)
- Affected endpoint(s) and time window

## Checks

1. **Backend problem details**:
   - Storage errors are mapped to stable HTTP semantics (400/404/409/503).
2. **CloudWatch**:
   - DynamoDB `ThrottledRequests`, `SuccessfulRequestLatency`
3. **Hot partition diagnosis**:
   - Look for a single pk prefix being hammered (e.g. job polling storms).

## Mitigations

- Reduce polling frequency on the frontend (backoff).
- Add request-side caching where safe (ETags, memoized list calls).
- For sustained throttling, move hot read patterns to a dedicated GSI or introduce a cache layer.

## Follow-ups (hardening)

- Add alarms on DynamoDB throttling metrics.
- Add jittered backoff and circuit breaking on polling-heavy paths.
