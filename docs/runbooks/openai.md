# OpenAI / AI degradation

## Symptoms

- AI actions fail (edit text, generate content, proposal section generation)
- Very slow AI responses / timeouts
- Sudden cost spikes

## Evidence to collect

- **Reference ID** (`x-request-id`)
- The **feature** used (RFP upload analysis vs proposal generation vs inline edit)
- Time window and approximate frequency

## Checks

1. **Backend logs**: filter by `event=ai_text_failed` / `ai_json_failed` / `ai_call_ok`.
2. **Circuit breaker state**:
   - If upstream errors repeat, the AI client can short-circuit with `ai_temporarily_unavailable`.
3. **Model routing**:
   - Validate `OPENAI_MODEL` and the per-purpose overrides (`OPENAI_MODEL_*`).
4. **Token / output guardrails**:
   - Validate `OPENAI_MAX_OUTPUT_TOKENS_CAP` is set to a sane value (default 4000).

## Mitigations

- If OpenAI is degraded:
  - Defer heavy work to async jobs (proposal section generation already uses a job endpoint).
  - Ask users to retry later; reduce concurrency; consider temporarily switching to a cheaper/faster model via env override.
- If cost spike:
  - Lower `OPENAI_MAX_OUTPUT_TOKENS_CAP`.
  - Route heavy purposes to a cheaper model via per-purpose override.

## Follow-ups (hardening)

- Add alerts for:
  - sustained AI 5xx/429 rates
  - increased p95 latency on AI-heavy endpoints
- Add per-purpose budgets and dashboards (tokens/min and cost attribution).
