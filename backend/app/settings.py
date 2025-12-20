from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    # Runtime
    environment: str = Field(default="development", validation_alias="NODE_ENV")
    port: int = Field(default=8080, validation_alias="PORT")

    # CORS / Frontend
    frontend_base_url: str = Field(
        default="https://rfp.polariseco.com", validation_alias="FRONTEND_BASE_URL"
    )
    frontend_url: str | None = Field(default=None, validation_alias="FRONTEND_URL")
    frontend_urls: str | None = Field(default=None, validation_alias="FRONTEND_URLS")

    # AWS / data
    aws_region: str = Field(default="us-east-1", validation_alias="AWS_REGION")
    ddb_table_name: str | None = Field(default=None, validation_alias="DDB_TABLE_NAME")
    assets_bucket_name: str | None = Field(
        default=None, validation_alias="ASSETS_BUCKET_NAME"
    )

    # Auth (Cognito)
    cognito_user_pool_id: str | None = Field(
        default=None, validation_alias="COGNITO_USER_POOL_ID"
    )
    cognito_client_id: str | None = Field(
        default=None, validation_alias="COGNITO_CLIENT_ID"
    )
    cognito_region: str = Field(default="us-east-1", validation_alias="COGNITO_REGION")

    # Auth (Magic link)
    magic_link_table_name: str | None = Field(
        default=None, validation_alias="MAGIC_LINK_TABLE_NAME"
    )

    # Auth (Email allowlist)
    allowed_email_domain: str = Field(
        default="polariseco.com", validation_alias="ALLOWED_EMAIL_DOMAIN"
    )

    # Misc integrations
    openai_api_key: str | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    # Optional: force OpenAI project/org for requests (prevents “wrong project” surprises).
    openai_project_id: str | None = Field(default=None, validation_alias="OPENAI_PROJECT_ID")
    openai_organization_id: str | None = Field(default=None, validation_alias="OPENAI_ORG_ID")
    # GPT-5.2 is our default for backend AI workloads.
    openai_model: str = Field(default="gpt-5.2", validation_alias="OPENAI_MODEL")
    openai_model_rfp_analysis: str | None = Field(default=None, validation_alias="OPENAI_MODEL_RFP_ANALYSIS")
    openai_model_section_titles: str | None = Field(default=None, validation_alias="OPENAI_MODEL_SECTION_TITLES")
    openai_model_text_edit: str | None = Field(default=None, validation_alias="OPENAI_MODEL_TEXT_EDIT")
    openai_model_generate_content: str | None = Field(default=None, validation_alias="OPENAI_MODEL_GENERATE_CONTENT")
    openai_model_proposal_sections: str | None = Field(default=None, validation_alias="OPENAI_MODEL_PROPOSAL_SECTIONS")
    openai_model_buyer_enrichment: str | None = Field(default=None, validation_alias="OPENAI_MODEL_BUYER_ENRICHMENT")
    openai_model_slack_agent: str | None = Field(default=None, validation_alias="OPENAI_MODEL_SLACK_AGENT")
    openai_model_rfp_section_summary: str | None = Field(
        default=None, validation_alias="OPENAI_MODEL_RFP_SECTION_SUMMARY"
    )
    # Guardrail: clamp max output tokens (prevents accidental cost explosions).
    openai_max_output_tokens_cap: int = Field(
        default=4000, validation_alias="OPENAI_MAX_OUTPUT_TOKENS_CAP"
    )

    # GPT-5 family tuning knobs (Responses API).
    # - reasoning effort controls how much the model "thinks" before answering
    # - verbosity controls output length for text responses
    #
    # Defaults are chosen to optimize *data extraction quality* while keeping latency/cost reasonable:
    # - JSON extraction: low reasoning + low verbosity
    # - freeform writing: none reasoning (so temperature is supported) + medium verbosity
    openai_reasoning_effort: str = Field(default="none", validation_alias="OPENAI_REASONING_EFFORT")
    openai_reasoning_effort_json: str = Field(
        default="low", validation_alias="OPENAI_REASONING_EFFORT_JSON"
    )
    openai_reasoning_effort_text: str = Field(
        default="none", validation_alias="OPENAI_REASONING_EFFORT_TEXT"
    )
    openai_text_verbosity: str = Field(default="medium", validation_alias="OPENAI_TEXT_VERBOSITY")
    openai_text_verbosity_json: str = Field(
        default="low", validation_alias="OPENAI_TEXT_VERBOSITY_JSON"
    )

    # Slack (optional; enables /api/integrations/slack/*)
    slack_enabled: bool = Field(default=False, validation_alias="SLACK_ENABLED")
    slack_bot_token: str | None = Field(default=None, validation_alias="SLACK_BOT_TOKEN")
    slack_signing_secret: str | None = Field(default=None, validation_alias="SLACK_SIGNING_SECRET")
    slack_default_channel: str | None = Field(default=None, validation_alias="SLACK_DEFAULT_CHANNEL")
    # Optional: dedicated channel for machine-emitted RFP upload notifications.
    # Can be a channel ID (recommended) or name (e.g. "rfp-machine").
    slack_rfp_machine_channel: str | None = Field(
        default="rfp-machine", validation_alias="SLACK_RFP_MACHINE_CHANNEL"
    )
    # Prefer injecting a single Secrets Manager ARN and resolving keys at runtime.
    slack_secret_arn: str | None = Field(default=None, validation_alias="SLACK_SECRET_ARN")

    # Slack agent (LLM-powered Q&A)
    slack_agent_enabled: bool = Field(default=True, validation_alias="SLACK_AGENT_ENABLED")
    slack_agent_actions_enabled: bool = Field(
        default=True, validation_alias="SLACK_AGENT_ACTIONS_ENABLED"
    )

    # Canva Connect (integration)
    canva_client_id: str | None = Field(default=None, validation_alias="CANVA_CLIENT_ID")
    canva_client_secret: str | None = Field(
        default=None, validation_alias="CANVA_CLIENT_SECRET"
    )
    canva_redirect_uri: str | None = Field(default=None, validation_alias="CANVA_REDIRECT_URI")
    canva_token_enc_key: str | None = Field(default=None, validation_alias="CANVA_TOKEN_ENC_KEY")

    # Legacy JWT secret still used for signed state in integrations (optional)
    jwt_secret: str | None = Field(default=None, validation_alias="JWT_SECRET")

    # Observability (OpenTelemetry)
    otel_enabled: bool = Field(default=False, validation_alias="OTEL_ENABLED")
    otel_service_name: str | None = Field(
        default="polaris-rfp-backend", validation_alias="OTEL_SERVICE_NAME"
    )
    # OTLP/HTTP endpoint (e.g. http://adot-collector:4318/v1/traces)
    otel_exporter_otlp_endpoint: str | None = Field(
        default=None, validation_alias="OTEL_EXPORTER_OTLP_ENDPOINT"
    )

    # ---- helpers / derived flags ----
    @property
    def normalized_environment(self) -> str:
        v = (self.environment or "").strip().lower()
        if v in ("prod", "production"):
            return "production"
        if v in ("stage", "staging"):
            return "staging"
        if v in ("dev", "development"):
            return "development"
        return v or "development"

    @property
    def is_production(self) -> bool:
        return self.normalized_environment == "production"

    @property
    def is_development(self) -> bool:
        return self.normalized_environment == "development"

    def require_in_production(self) -> None:
        """
        Enforce required settings in production.

        Development/staging are allowed to run with partial config for local work,
        but production must be fully configured.
        """
        if not self.is_production:
            return

        missing: list[str] = []

        # Core auth
        if not self.cognito_user_pool_id:
            missing.append("COGNITO_USER_POOL_ID")
        if not self.cognito_client_id:
            missing.append("COGNITO_CLIENT_ID")

        # Magic link flow depends on DynamoDB
        if not self.magic_link_table_name:
            missing.append("MAGIC_LINK_TABLE_NAME")

        # Crypto: encryption must never fall back to an insecure default in prod.
        # We accept either CANVA_TOKEN_ENC_KEY (preferred) or JWT_SECRET (legacy).
        if not (self.canva_token_enc_key or self.jwt_secret):
            missing.append("CANVA_TOKEN_ENC_KEY (or JWT_SECRET)")

        # Slack (optional) - but if explicitly enabled, require full config.
        if bool(self.slack_enabled):
            # Allow either direct env vars or a Secrets Manager ARN.
            if not (self.slack_secret_arn and str(self.slack_secret_arn).strip()):
                if not self.slack_bot_token:
                    missing.append("SLACK_BOT_TOKEN (or SLACK_SECRET_ARN)")
                if not self.slack_signing_secret:
                    missing.append("SLACK_SIGNING_SECRET (or SLACK_SECRET_ARN)")
                if not self.slack_default_channel:
                    missing.append("SLACK_DEFAULT_CHANNEL (or SLACK_SECRET_ARN)")

        if missing:
            raise RuntimeError(
                "Missing required production environment variables: "
                + ", ".join(missing)
            )

    def to_log_safe_dict(self) -> dict[str, object]:
        """
        A redacted representation safe for structured logs / diagnostics.
        """
        def _has(v: object) -> bool:
            return v is not None and str(v).strip() != ""

        return {
            "environment": self.normalized_environment,
            "port": self.port,
            "frontend": {
                "frontend_base_url": self.frontend_base_url,
                "frontend_url": self.frontend_url,
                "frontend_urls": self.frontend_urls,
            },
            "aws": {
                "aws_region": self.aws_region,
                "ddb_table_name": self.ddb_table_name,
                "assets_bucket_name": self.assets_bucket_name,
            },
            "auth": {
                "cognito_user_pool_id": self.cognito_user_pool_id,
                "cognito_client_id": self.cognito_client_id,
                "cognito_region": self.cognito_region,
                "magic_link_table_name": self.magic_link_table_name,
            },
            "integrations": {
                "openai_api_key_configured": _has(self.openai_api_key),
                "openai_project_id_configured": _has(self.openai_project_id),
                "openai_organization_id_configured": _has(self.openai_organization_id),
                "openai_model": self.openai_model,
                "openai_reasoning_effort": self.openai_reasoning_effort,
                "openai_reasoning_effort_json": self.openai_reasoning_effort_json,
                "openai_reasoning_effort_text": self.openai_reasoning_effort_text,
                "openai_text_verbosity": self.openai_text_verbosity,
                "openai_text_verbosity_json": self.openai_text_verbosity_json,
                "canva_client_id": self.canva_client_id,
                "canva_redirect_uri": self.canva_redirect_uri,
                "canva_client_secret_configured": _has(self.canva_client_secret),
                "canva_token_enc_key_configured": _has(self.canva_token_enc_key),
                "jwt_secret_configured": _has(self.jwt_secret),
                "slack_enabled": bool(self.slack_enabled),
                "slack_bot_token_configured": _has(self.slack_bot_token),
                "slack_signing_secret_configured": _has(self.slack_signing_secret),
                "slack_default_channel": self.slack_default_channel if _has(self.slack_default_channel) else None,
                "slack_secret_arn_configured": _has(self.slack_secret_arn),
            },
        }

    def openai_model_for(self, purpose: str) -> str:
        # Allow per-purpose override, else fall back to OPENAI_MODEL.
        purpose = (purpose or "").strip().lower()
        override_map = {
            "rfp_analysis": self.openai_model_rfp_analysis,
            # RFP analysis buckets share the same model override.
            "rfp_analysis_meta": self.openai_model_rfp_analysis,
            "rfp_analysis_dates": self.openai_model_rfp_analysis,
            "rfp_analysis_lists": self.openai_model_rfp_analysis,
            "section_titles": self.openai_model_section_titles,
            "text_edit": self.openai_model_text_edit,
            "generate_content": self.openai_model_generate_content,
            "proposal_sections": self.openai_model_proposal_sections,
            "buyer_enrichment": self.openai_model_buyer_enrichment,
            "slack_agent": self.openai_model_slack_agent,
            "rfp_section_summary": self.openai_model_rfp_section_summary,
        }
        ov = override_map.get(purpose)
        if ov and str(ov).strip():
            return str(ov).strip()
        return str(self.openai_model or "gpt-4o-mini").strip() or "gpt-4o-mini"

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    s = Settings()
    s.require_in_production()
    return s


# Backwards-compatible module-level singleton.
settings = get_settings()
