# Comprehensive Diagnostics System

## Overview

The comprehensive diagnostics system provides detailed health checks and status information for the Polaris RFP backend, including credentials, infrastructure resources, available tools, and agent capabilities.

## Access

### Slack Command

Use `/polaris diag` or `/polaris diagnostics` to get a full diagnostic report in Slack.

### Programmatic Access

```python
from backend.app.services.comprehensive_diagnostics import (
    get_comprehensive_diagnostics,
    format_diagnostics_for_slack
)

# Get raw diagnostics data
diagnostics = get_comprehensive_diagnostics()

# Format for Slack display
lines = format_diagnostics_for_slack(diagnostics)
```

## Diagnostic Sections

### 🔐 Credentials

Validates and reports status for all API keys and credentials:

- **OpenAI**: API key, model configuration, project/organization IDs
- **GitHub**: Token, repository configuration, allowed repos
- **Google Drive**: Service account and API key status
- **Slack**: Bot token, auth.test status, signing secret
- **Canva**: Client ID, client secret, redirect URI, token encryption key

**Status indicators**:

- ✅ = Configured and working
- ⚠️ = Configured but validation failed
- ❌ = Not configured or error

### 🏗️ Infrastructure

Reports on all infrastructure resources:

- **ECS**: Cluster, service, allowed clusters/services
- **DynamoDB**: Table count and names
- **S3**: Bucket count, names, and prefixes
- **CloudWatch Logs**: Log group count (including discovered at startup)
- **SQS**: Queue count
- **Cognito**: User pool count
- **Secrets Manager**: Secret ARN count

Also reports any load errors encountered during infrastructure discovery.

### 🛠️ Tools

Summarizes all available tools:

- Total tool count
- Tools grouped by category:
  - slack: Slack integration tools
  - dynamodb: DynamoDB operations
  - s3: S3 operations
  - aws: AWS services (ECS, SQS, Cognito, Secrets Manager)
  - github: GitHub API operations
  - telemetry: CloudWatch Logs queries
  - browser: Browser automation (Playwright)
  - memory: Agent memory operations
  - rfp: RFP-related tools
  - proposal: Proposal-related tools
  - jobs: Agent job management
  - opportunity: Opportunity state management
  - google: Google Drive integration
  - introspection: Capability discovery tools
  - external_context: External data sources (news, weather, research)
  - other: Miscellaneous tools

### 🧠 Capabilities

Reports on agent capabilities (if capability inventory is populated):

- Total capability count
- Capabilities grouped by category:
  - tool: Available tools
  - skill: Agent skills
  - domain: Domain-specific functions
  - repository: Repository methods
  - shared: Shared utilities

Also includes subcategory breakdowns.

## Implementation

### Core Module

**Location**: `backend/app/services/comprehensive_diagnostics.py`

**Main Functions**:

- `get_comprehensive_diagnostics()`: Collects all diagnostic data
- `format_diagnostics_for_slack()`: Formats diagnostics for Slack display

**Diagnostic Collectors**:

- `_get_credentials_diagnostics()`: Validates all credentials
- `_get_infrastructure_diagnostics()`: Queries infrastructure config
- `_get_tools_diagnostics()`: Counts and categorizes tools
- `_get_capabilities_diagnostics()`: Reports on capability inventory

### Integration Points

**Infrastructure Config**: Uses `agent_infrastructure_config.py` for infrastructure resource data

**Tool Registry**: Reads from `tools/registry/read_registry.py` for tool listing

**Capability Inventory**: Uses `shared/introspection/capability_inventory.py` for capability data

**Settings**: Reads from `settings.py` for credential configuration

### Slack Command

**Location**: `backend/app/routers/integrations_slack.py`

The `/polaris diag` command:

1. Calls comprehensive diagnostics
2. Formats output for Slack
3. Adds Slack-specific connection and identity mapping info
4. Includes troubleshooting tips
5. Falls back to basic diagnostics if comprehensive fails

## Error Handling

All diagnostic collectors handle errors gracefully:

- Credential validation failures are reported with error messages
- Infrastructure discovery errors are logged but don't block diagnostics
- Tool listing errors are caught and reported
- Capability inventory errors are non-fatal (inventory may not be populated)

The system always returns some diagnostic information, even if some sections fail.

## Example Output

```
*Polaris Slack Diagnostics*

*🔗 Slack Connection*
- slack_enabled: `True`
- slack_agent_enabled: `True`
- bot_token_present: `True`
- auth.test: `True`
- users.info: `True`

*👤 Identity Mapping*
- slack_user_id: `U123456`
- display_name: `Wes`
- email: `wes@example.com`
- user_sub: `abc-123-def`

*🔐 Credentials*
- OpenAI: ✅ (model: `gpt-5.2`)
  - Project ID: configured
- GitHub: ✅ (repo: `org/repo`)
  - Allowed repos: 3
- Google Drive: ✅ (method: `service_account`)
- Slack: ✅ (token: ok, auth: ok)
- Canva: ✅

*🏗️ Infrastructure*
- ECS: cluster=`my-cluster`, service=`backend-service`
  - Allowed clusters: 2
  - Allowed services: 5
- DynamoDB: 8 tables
  - Tables: table1, table2, table3, table4, table5... (+3 more)
- S3: 3 buckets, 2 prefixes
  - Buckets: bucket1, bucket2, bucket3
- CloudWatch Logs: 15 log groups (10 discovered at startup)
- SQS: 4 queues
- Cognito: 1 user pools
- Secrets Manager: 12 ARNs

*🛠️ Tools*
- Total tools: 145
- By category:
  - aws: 25
  - slack: 12
  - dynamodb: 8
  - github: 15
  - memory: 10
  - rfp: 18
  - ...

*🧠 Capabilities*
- Total capabilities: 230
- By category:
  - tool: 145
  - skill: 45
  - domain: 30
  - repository: 10
  - shared: 0

*💡 Tips*
- If `users.info` fails with `missing_scope`, add `users:read` (and `users:read.email` for email mapping), then reinstall.
- Check credentials section above for API key status.
- Use `/polaris diag` to see this full diagnostic report.
```

## Future Enhancements

Potential additions:

- Database connection health checks
- API endpoint availability tests
- Performance metrics (response times, error rates)
- Resource usage (memory, CPU, disk)
- Recent error logs summary
- Configuration drift detection
- Security status (SSL certificates, secrets rotation dates)
