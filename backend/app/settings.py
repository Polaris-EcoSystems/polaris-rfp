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

    # Misc integrations
    openai_api_key: str | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", validation_alias="OPENAI_MODEL")
    openai_model_rfp_analysis: str | None = Field(default=None, validation_alias="OPENAI_MODEL_RFP_ANALYSIS")
    openai_model_section_titles: str | None = Field(default=None, validation_alias="OPENAI_MODEL_SECTION_TITLES")
    openai_model_text_edit: str | None = Field(default=None, validation_alias="OPENAI_MODEL_TEXT_EDIT")
    openai_model_generate_content: str | None = Field(default=None, validation_alias="OPENAI_MODEL_GENERATE_CONTENT")
    openai_model_proposal_sections: str | None = Field(default=None, validation_alias="OPENAI_MODEL_PROPOSAL_SECTIONS")
    openai_model_buyer_enrichment: str | None = Field(default=None, validation_alias="OPENAI_MODEL_BUYER_ENRICHMENT")

    # Canva Connect (integration)
    canva_client_id: str | None = Field(default=None, validation_alias="CANVA_CLIENT_ID")
    canva_client_secret: str | None = Field(
        default=None, validation_alias="CANVA_CLIENT_SECRET"
    )
    canva_redirect_uri: str | None = Field(default=None, validation_alias="CANVA_REDIRECT_URI")
    canva_token_enc_key: str | None = Field(default=None, validation_alias="CANVA_TOKEN_ENC_KEY")

    # Legacy JWT secret still used for signed state in integrations (optional)
    jwt_secret: str | None = Field(default=None, validation_alias="JWT_SECRET")

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
                "openai_model": self.openai_model,
                "canva_client_id": self.canva_client_id,
                "canva_redirect_uri": self.canva_redirect_uri,
                "canva_client_secret_configured": _has(self.canva_client_secret),
                "canva_token_enc_key_configured": _has(self.canva_token_enc_key),
                "jwt_secret_configured": _has(self.jwt_secret),
            },
        }

    def openai_model_for(self, purpose: str) -> str:
        # Allow per-purpose override, else fall back to OPENAI_MODEL.
        purpose = (purpose or "").strip().lower()
        override_map = {
            "rfp_analysis": self.openai_model_rfp_analysis,
            "section_titles": self.openai_model_section_titles,
            "text_edit": self.openai_model_text_edit,
            "generate_content": self.openai_model_generate_content,
            "proposal_sections": self.openai_model_proposal_sections,
            "buyer_enrichment": self.openai_model_buyer_enrichment,
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
