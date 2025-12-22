# Google Drive Credentials Validation

## Overview

Google Drive credentials are now validated at application startup and their status can be checked via the Slack bot diagnostics command.

## Credential Types

The Google Drive integration uses two types of credentials:

1. **Service Account JSON** (Preferred)

   - Secret: `GOOGLE_CREDENTIALS` (`arn:aws:secretsmanager:us-east-1:211125621822:secret:GOOGLE_CREDENTIALS-lqF0A9`)
   - Type: Service account JSON credentials
   - Scope: `https://www.googleapis.com/auth/drive` (full Drive access)
   - Used for: All CRUDL operations (Create, Read, Update, Delete, List)

2. **API Key** (Fallback)
   - Secret: `GOOGLE_API_KEY` (`arn:aws:secretsmanager:us-east-1:211125621822:secret:GOOGLE_API_KEY-yPu460`)
   - Type: Simple API key string
   - Used for: Limited read-only operations (fallback if service account fails)

## Startup Validation

Credentials are validated during application startup via the `InfrastructureConfig` system:

- **Location**: `backend/app/services/agent_infrastructure_config.py`
- **Method**: `_validate_google_drive_credentials()`
- **Checks**:
  - Service account JSON can be loaded from Secrets Manager
  - Service account JSON is valid and can be parsed
  - API key can be loaded from Secrets Manager (if service account fails)

**Note**: Validation only checks that credentials can be _loaded_ (not that they actually work). Full validation (API call test) happens on first use via the tools.

## Infrastructure Config Fields

The `InfrastructureConfig` class now includes:

```python
# Google Drive configuration
google_drive_service_account_configured: bool = False
google_drive_api_key_configured: bool = False
google_drive_credentials_valid: bool = False
google_drive_credentials_error: str | None = None
```

These fields are populated at startup and accessible via:

- `get_infrastructure_config().google_drive_service_account_configured`
- `get_infrastructure_config().google_drive_api_key_configured`
- `get_infrastructure_config().google_drive_credentials_valid`
- `get_infrastructure_config().google_drive_credentials_error`

## Infrastructure Config Summary

Google Drive status is included in the infrastructure config summary (accessible via `infrastructure_config_summary` tool):

```json
{
  "googleDrive": {
    "serviceAccountConfigured": true,
    "apiKeyConfigured": false,
    "credentialsValid": true,
    "error": null
  }
}
```

## Slack Diagnostics Command

The `/polaris diag` (or `/polaris diagnostics`) command now includes Google Drive credential status:

```
*Google Drive*
- credentials_status: `service_account` (or `api_key`, `invalid`, `error`, `unknown`)
- credentials_error: `...` (only shown if there's an error)
```

**Status values**:

- `service_account`: Service account credentials are configured and valid
- `api_key`: API key is configured (service account not available)
- `invalid`: Credentials exist but validation failed
- `error`: Error occurred during validation
- `unknown`: Status could not be determined

## Implementation Details

### Validation Logic

1. **Service Account (Preferred)**

   - Tries to load credentials via `_get_google_credentials(use_api_key=False)`
   - Validates JSON can be parsed and credentials object can be created
   - Marks as configured if successful

2. **API Key (Fallback)**
   - Only checked if service account fails
   - Tries to load API key via `_get_google_credentials(use_api_key=True)`
   - Validates it's a non-empty string
   - Marks as configured if successful

### Error Handling

- All errors are caught and stored in `google_drive_credentials_error`
- Validation failures are logged but don't block application startup
- Errors are included in infrastructure config summary for debugging

## Usage Examples

### Check Status via Slack

```
/polaris diag
```

Shows Google Drive credential status in the diagnostics output.

### Check Status via API

```python
from app.services.agent_infrastructure_config import get_infrastructure_config

config = get_infrastructure_config()
summary = config.get_summary()
gd_status = summary.get("googleDrive", {})

print(f"Service Account: {gd_status.get('serviceAccountConfigured')}")
print(f"API Key: {gd_status.get('apiKeyConfigured')}")
print(f"Valid: {gd_status.get('credentialsValid')}")
if gd_status.get('error'):
    print(f"Error: {gd_status.get('error')}")
```

### Check Status via Agent Tool

Agents can use the `infrastructure_config_summary` tool to get Google Drive status along with other infrastructure configuration.

## Troubleshooting

If credentials status shows as `invalid` or `error`:

1. **Check Secrets Manager**

   - Verify `GOOGLE_CREDENTIALS` secret exists and contains valid service account JSON
   - Verify `GOOGLE_API_KEY` secret exists (if using fallback)
   - Check ECS task has permissions to access these secrets

2. **Check Service Account**

   - Verify service account JSON is valid JSON format
   - Verify service account has Drive API enabled
   - Verify service account has proper IAM permissions

3. **Check Logs**

   - Look for `google_drive_service_account_not_configured` or `google_drive_api_key_not_configured` log entries
   - Check for errors during infrastructure config loading

4. **Validate Credentials Work**
   - Use the `google_read_doc` tool to test credentials actually work
   - Check CloudWatch Logs for Google Drive API errors

## Related Files

- `backend/app/services/agent_infrastructure_config.py` - Infrastructure config with validation
- `backend/app/tools/categories/google/google_drive.py` - Google Drive tools and credential loading
- `backend/app/routers/integrations_slack.py` - Slack diagnostics command
