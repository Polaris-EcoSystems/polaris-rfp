from __future__ import annotations

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

    # Canva Connect (integration)
    canva_client_id: str | None = Field(default=None, validation_alias="CANVA_CLIENT_ID")
    canva_client_secret: str | None = Field(
        default=None, validation_alias="CANVA_CLIENT_SECRET"
    )
    canva_redirect_uri: str | None = Field(default=None, validation_alias="CANVA_REDIRECT_URI")
    canva_token_enc_key: str | None = Field(default=None, validation_alias="CANVA_TOKEN_ENC_KEY")

    # Legacy JWT secret still used for signed state in integrations (optional)
    jwt_secret: str | None = Field(default=None, validation_alias="JWT_SECRET")


settings = Settings()  # singleton
