# Backend Documentation

Comprehensive documentation for the Polaris RFP Backend, covering API endpoints, Slack integration, and AI agent functionalities.

## Table of Contents

1. [Overview](#overview)
2. [API Endpoints](#api-endpoints)
3. [Slack Integration](#slack-integration)
4. [AI Agent System](#ai-agent-system)
5. [Architecture](#architecture)

---

## Overview

The Polaris RFP Backend is a FastAPI-based service providing:

- **RFP Management**: Upload, analyze, and manage RFPs (Request for Proposals)
- **Proposal Generation**: AI-powered proposal creation and editing
- **Content Management**: Company profiles, team members, references
- **Workflow Management**: Task tracking and pipeline stages
- **Slack Integration**: Comprehensive Slack bot with commands, events, and AI agents
- **AI Agents**: Advanced AI agent system with memory, context, and tool execution
- **Contracting**: Post-proposal contracting case management

---

## API Endpoints

All API endpoints are prefixed with `/api` unless otherwise noted. Authentication is required for most endpoints using Cognito JWT tokens via the `Authorization: Bearer <token>` header.

### Authentication (`/api/auth`)

#### Magic Link Authentication (Primary Method)

- **POST `/api/auth/magic-link/request`**

  - Request a magic link login
  - Body: `{ "email": "user@domain.com", "username": "optional", "returnTo": "/path" }`
  - Returns: `{ "ok": true }`
  - Sends email with magic link code

- **POST `/api/auth/magic-link/verify`**
  - Verify magic link code and create session
  - Body: `{ "magicId": "optional", "email": "optional", "code": "123456", "remember": true }`
  - Returns: `{ "access_token": "...", "token_type": "bearer", "sid": "...", "session_expires_at": 1234567890 }`

#### Session Management

- **POST `/api/auth/session/refresh`**

  - Refresh access token using server-side session
  - Headers: `X-Session-Id: <sid>`
  - Returns: `{ "access_token": "...", "token_type": "bearer" }`

- **POST `/api/auth/session/logout`**

  - Logout and delete session
  - Headers: `X-Session-Id: <sid>`
  - Returns: `{ "ok": true }`

- **GET `/api/auth/sessions`**

  - List all active sessions for current user
  - Returns: `{ "data": [{ "sid": "...", "sessionKind": "...", "createdAt": 123, ... }] }`

- **POST `/api/auth/sessions/revoke`**

  - Revoke a specific session
  - Body: `{ "sid": "..." }`

- **POST `/api/auth/sessions/revoke-all`**

  - Revoke all sessions except current

- **GET `/api/auth/me`**
  - Get current authenticated user info
  - Returns: `{ "sub": "...", "username": "...", "email": "...", "display_name": "..." }`

#### Password Reset (Legacy)

- **POST `/api/auth/request-password-reset`**

  - Request password reset token
  - Body: `{ "email": "user@domain.com" }`

- **POST `/api/auth/reset-password`**
  - Reset password with token
  - Body: `{ "token": "...", "password": "..." }`

### RFPs (`/api/rfp`)

#### RFP Upload & Analysis

- **POST `/api/rfp/upload`**

  - Upload and analyze PDF RFP
  - Body: `multipart/form-data` with `file` field (PDF)
  - Returns: Complete RFP object with extracted data

- **POST `/api/rfp/upload/presign`**

  - Get presigned S3 URL for direct upload
  - Body: `{ "fileName": "...", "contentType": "application/pdf", "sha256": "..." }`
  - Returns: `{ "putUrl": "...", "bucket": "...", "key": "...", "duplicate": false }`

- **POST `/api/rfp/upload/from-s3`**

  - Trigger analysis of uploaded S3 file
  - Body: `{ "key": "...", "fileName": "...", "sha256": "..." }`
  - Returns: `{ "ok": true, "job": { "jobId": "...", "status": "queued" } }`

- **GET `/api/rfp/upload/jobs/{jobId}`**

  - Get upload job status
  - Returns: `{ "ok": true, "job": { "jobId": "...", "status": "...", "rfpId": "..." } }`

- **POST `/api/rfp/analyze-url`**

  - Analyze RFP from URL
  - Body: `{ "url": "https://..." }`
  - Returns: RFP object

- **POST `/api/rfp/analyze-urls`**
  - Analyze multiple RFPs from URLs
  - Body: `{ "urls": ["https://...", "https://..."] }`
  - Returns: `{ "results": [{ "url": "...", "ok": true, "rfp": {...} }] }`

#### RFP Management

- **GET `/api/rfp/`**

  - List all RFPs with pagination
  - Query params: `page=1`, `limit=20`, `nextToken=...`
  - Returns: `{ "data": [...], "nextToken": "..." }`

- **GET `/api/rfp/search/{query}`**

  - Search RFPs by title/client/type
  - Returns: Array of matching RFPs

- **GET `/api/rfp/{id}`**

  - Get single RFP by ID
  - Returns: Complete RFP object with attachments

- **PUT `/api/rfp/{id}`**

  - Update RFP
  - Body: Partial RFP object
  - Returns: Updated RFP

- **DELETE `/api/rfp/{id}`**
  - Delete RFP

#### AI-Enhanced Analysis

- **GET `/api/rfp/{id}/ai-refresh/stream`**

  - Stream incremental AI extraction updates (SSE)
  - Events: `meta`, `dates`, `lists`, `done`, `error`
  - Updates RFP with extracted metadata, dates, and lists

- **GET `/api/rfp/{id}/ai-summary/stream`**

  - Stream AI-generated summary (SSE)
  - Events: `hello`, `delta`, `done`, `error`
  - Persists summary to RFP

- **POST `/api/rfp/{id}/ai-section-titles`**

  - Generate section titles for proposal scaffolding
  - Returns: `{ "titles": ["Section 1", "Section 2", ...] }`

- **POST `/api/rfp/{id}/ai-section-summary`**

  - Generate section-specific summary
  - Body: `{ "sectionId": "...", "topic": "...", "force": false }`
  - Returns: `{ "sectionId": "...", "summary": "...", "cached": false }`

- **POST `/api/rfp/{id}/ai-reanalyze`**
  - Re-run RFP analysis on stored rawText
  - Returns: Updated RFP

#### RFP Review

- **PUT `/api/rfp/{id}/review`**
  - Update bid/no-bid review decision
  - Body: `{ "decision": "bid" | "no_bid" | "maybe" | "", "notes": "...", "reasons": [...], "blockers": [...], "requirements": [...], "assignedReviewerUserSub": "..." }`
  - Returns: Updated RFP

#### RFP Utilities

- **GET `/api/rfp/{id}/source-pdf/presign`**

  - Get presigned URL for original uploaded PDF
  - Returns: `{ "url": "...", "expiresInSeconds": 3600 }`

- **GET `/api/rfp/{id}/proposals`**

  - List all proposals for RFP
  - Returns: `{ "data": [...] }`

- **POST `/api/rfp/{id}/buyer-profiles/remove`**
  - Remove buyer profiles
  - Body: `{ "selected": [...], "clear": false }`

### Proposals (`/api/proposals`)

#### Proposal Generation

- **POST `/api/proposals/generate`**

  - Generate new proposal from RFP
  - Body: `{ "rfpId": "...", "templateId": "...", "title": "...", "companyId": "...", "customContent": {...}, "async": false }`
  - Returns: Proposal object with generated sections

- **POST `/api/proposals/{id}/generate-sections`**

  - Regenerate all proposal sections with AI
  - Returns: `{ "message": "...", "sections": {...}, "proposal": {...} }`

- **POST `/api/proposals/{id}/generate-sections/async`**
  - Async section generation (creates job, returns immediately)
  - Returns: `{ "ok": true, "job": {...}, "proposal": {...} }`

#### Proposal Management

- **GET `/api/proposals/`**

  - List all proposals
  - Query params: `page=1`, `limit=20`, `nextToken=...`
  - Returns: `{ "data": [...], "nextToken": "..." }`

- **GET `/api/proposals/{id}`**

  - Get proposal by ID
  - Returns: Complete proposal with sections

- **PUT `/api/proposals/{id}`**

  - Update proposal
  - Body: Partial proposal object
  - Returns: Updated proposal

- **DELETE `/api/proposals/{id}`**
  - Delete proposal

#### Proposal Content

- **PUT `/api/proposals/{id}/content-library/{sectionName}`**

  - Update section from content library
  - Body: `{ "selectedIds": [...], "type": "company" | "team" | "references" }`
  - Returns: Updated proposal

- **PUT `/api/proposals/{id}/company`**

  - Switch company and regenerate company-related sections
  - Body: `{ "companyId": "..." }`
  - Returns: Updated proposal

- **PUT `/api/proposals/{id}/review`**
  - Update proposal review
  - Body: `{ "score": 85, "notes": "...", "rubric": {...}, "decision": "shortlist" | "reject" | "" }`
  - Returns: Updated proposal

#### Proposal Export

- **GET `/api/proposals/{id}/export-pdf`**

  - Export proposal as PDF
  - Returns: PDF file download

- **GET `/api/proposals/{id}/export/pdf`**

  - Alternative PDF export endpoint

- **GET `/api/proposals/{id}/export-docx`**
  - Export proposal as DOCX
  - Returns: DOCX file download

### Templates (`/api/templates`)

- **GET `/api/templates/`**

  - List all templates (builtin + custom)
  - Returns: `{ "data": [...], "builtin": [...], "templates": [...] }`

- **GET `/api/templates/{templateId}`**

  - Get template by ID
  - Returns: Template object with sections

- **POST `/api/templates/`**

  - Create new template
  - Body: `{ "name": "...", "projectType": "...", "sections": [...] }`
  - Returns: Created template

- **PUT `/api/templates/{templateId}`**

  - Update template
  - Body: Partial template object
  - Returns: Updated template

- **DELETE `/api/templates/{templateId}`**
  - Delete template

### Content Library (`/api/content`)

#### Companies

- **GET `/api/content/companies`**

  - List all companies
  - Returns: `{ "data": [...] }`

- **GET `/api/content/companies/{companyId}`**

  - Get company by ID
  - Returns: Company object

- **POST `/api/content/companies`**

  - Create company
  - Body: Company object
  - Returns: Created company

- **PUT `/api/content/companies/{companyId}`**

  - Update company
  - Body: Partial company object
  - Returns: Updated company

- **POST `/api/content/companies/{companyId}/regenerate-capabilities`**
  - Regenerate company capabilities using AI

#### Team Members

- **GET `/api/content/team-members`**

  - List all team members
  - Returns: `{ "data": [...] }`

- **GET `/api/content/team-members/{memberId}`**

  - Get team member by ID
  - Returns: Team member object

- **POST `/api/content/team-members`**

  - Create team member
  - Body: Team member object
  - Returns: Created team member

- **PUT `/api/content/team-members/{memberId}`**

  - Update team member
  - Body: Partial team member object
  - Returns: Updated team member

- **POST `/api/content/team-members/{memberId}/headshot/presign`**
  - Get presigned URL for headshot upload
  - Returns: `{ "putUrl": "...", "key": "..." }`

#### Project References

- **GET `/api/content/project-references`**

  - List all project references
  - Returns: `{ "data": [...] }`

- **GET `/api/content/project-references/{referenceId}`**

  - Get reference by ID
  - Returns: Reference object

- **POST `/api/content/project-references`**

  - Create reference
  - Body: Reference object
  - Returns: Created reference

- **PUT `/api/content/project-references/{referenceId}`**
  - Update reference
  - Body: Partial reference object
  - Returns: Updated reference

### AI Services (`/api/ai`)

- **POST `/api/ai/edit-text`**

  - Edit text using AI
  - Body: `{ "text": "...", "selectedText": "...", "prompt": "make it more professional" }`
  - Returns: `{ "editedText": "...", "originalText": "...", "prompt": "..." }`

- **POST `/api/ai/generate-content`**
  - Generate new content using AI
  - Body: `{ "prompt": "...", "context": "...", "contentType": "general" }`
  - Returns: `{ "content": "...", "prompt": "...", "contentType": "..." }`

### AI Agent API (`/api/ai`)

- **POST `/api/ai/ask`**

  - Ask conversational agent question
  - Body: `{ "question": "..." }`
  - Returns: `{ "ok": true, "text": "...", "blocks": [...], "meta": {...} }`

- **POST `/api/ai/propose`**

  - Propose an action (approval-gated)
  - Body: `{ "kind": "...", "args": {...}, "summary": "...", "ttlSeconds": 900 }`
  - Returns: `{ "ok": true, "action": { "actionId": "...", ... } }`

- **POST `/api/ai/confirm`**

  - Confirm and execute proposed action
  - Body: `{ "actionId": "..." }`
  - Returns: `{ "ok": true, "actionId": "...", "kind": "...", "result": {...} }`

- **POST `/api/ai/cancel`**

  - Cancel proposed action
  - Body: `{ "actionId": "..." }`
  - Returns: `{ "ok": true, "cancelled": true }`

- **GET `/api/ai/diagnostics`**
  - Get agent diagnostics
  - Query params: `hours=24`, `user_sub=...`, `rfp_id=...`, `channel_id=...`, `use_cache=true`, `force_refresh=false`
  - Returns: Diagnostic metrics and activities

### Tasks (`/api`)

- **GET `/api/rfps/{rfpId}/tasks`** or **GET `/api/rfp/{rfpId}/tasks`**

  - List tasks for RFP
  - Returns: `{ "data": [...] }`

- **POST `/api/rfps/{rfpId}/tasks/seed`** or **POST `/api/rfp/{rfpId}/tasks/seed`**

  - Seed tasks for current pipeline stage
  - Returns: `{ "ok": true, "rfpId": "...", "stage": "...", "createdCount": 5, ... }`

- **POST `/api/tasks/{taskId}/assign`**

  - Assign task to user
  - Body: `{ "assigneeUserSub": "...", "assigneeDisplayName": "..." }`
  - Returns: `{ "ok": true, "task": {...} }`

- **POST `/api/tasks/{taskId}/complete`**

  - Mark task as complete
  - Body: `{}`
  - Returns: `{ "ok": true, "task": {...} }`

- **POST `/api/tasks/{taskId}/reopen`**

  - Reopen completed task
  - Returns: `{ "ok": true, "task": {...} }`

- **GET `/api/tasks/{taskId}`**
  - Get task by ID
  - Returns: `{ "ok": true, "task": {...} }`

### Contracting (`/api`)

- **GET `/api/contracting/by-proposal/{proposalId}`**

  - Get contracting case by proposal ID
  - Returns: `{ "ok": true, "case": {...} }`

- **GET `/api/contracting/{caseId}`**

  - Get contracting case by ID
  - Returns: `{ "ok": true, "case": {...} }`

- **PUT `/api/contracting/{caseId}`**

  - Update contracting case
  - Body: Partial case object (includes key terms validation)
  - Returns: `{ "ok": true, "case": {...} }`

- **GET `/api/contracting/{caseId}/contract/versions`**

  - List contract document versions
  - Returns: `{ "ok": true, "data": [...] }`

- **GET `/api/contracting/{caseId}/contract/versions/{versionId}/presign`**

  - Get presigned URL for contract download
  - Query params: `expiresIn=900`
  - Returns: `{ "ok": true, "url": "...", "expiresIn": 900 }`

- **GET `/api/contracting/{caseId}/budget/versions`**

  - List budget versions
  - Returns: `{ "ok": true, "data": [...] }`

- **GET `/api/contracting/{caseId}/budget/versions/{versionId}/presign`**

  - Get presigned URL for budget download
  - Returns: `{ "ok": true, "url": "...", "expiresIn": 900 }`

- **POST `/api/contracting/{caseId}/contract/generate`**

  - Generate contract document (async job)
  - Body: `{ "templateId": "...", "keyTerms": {...} }`
  - Returns: `{ "ok": true, "job": {...} }`

- **POST `/api/contracting/{caseId}/budget/generate`**

  - Generate budget workbook (async job)
  - Body: `{ "lineItems": [...], "templateId": "..." }`
  - Returns: `{ "ok": true, "job": {...} }`

- **GET `/api/contracting/{caseId}/supporting-docs`**

  - List supporting documents
  - Returns: `{ "ok": true, "data": [...] }`

- **POST `/api/contracting/{caseId}/supporting-docs/presign`**

  - Get presigned URL for supporting doc upload
  - Body: `{ "fileName": "...", "contentType": "..." }`
  - Returns: `{ "ok": true, "putUrl": "...", "key": "..." }`

- **POST `/api/contracting/{caseId}/supporting-docs/from-s3`**

  - Register uploaded supporting document
  - Body: `{ "key": "...", "fileName": "...", "docId": "..." }`
  - Returns: `{ "ok": true, "doc": {...} }`

- **POST `/api/contracting/{caseId}/client-packages`**

  - Create client portal package
  - Body: `{ "name": "...", "expiresAt": "..." }`
  - Returns: `{ "ok": true, "package": {...} }`

- **GET `/api/contracting/{caseId}/client-packages`**

  - List client packages
  - Returns: `{ "ok": true, "data": [...] }`

- **POST `/api/contracting/{caseId}/client-packages/{packageId}/publish`**

  - Publish client package
  - Returns: `{ "ok": true, "package": {...} }`

- **POST `/api/contracting/{caseId}/client-packages/{packageId}/rotate-token`**

  - Rotate client package access token
  - Returns: `{ "ok": true, "package": {...} }`

- **POST `/api/contracting/{caseId}/client-packages/{packageId}/revoke`**

  - Revoke client package
  - Returns: `{ "ok": true }`

- **POST `/api/contracting/{caseId}/esign/envelopes`**

  - Create e-signature envelope
  - Body: `{ "recipients": [...], "documentId": "..." }`
  - Returns: `{ "ok": true, "envelope": {...} }`

- **GET `/api/contracting/{caseId}/esign/envelopes`**

  - List e-signature envelopes
  - Returns: `{ "ok": true, "data": [...] }`

- **POST `/api/contracting/{caseId}/esign/envelopes/{envelopeId}/send`**

  - Send e-signature envelope
  - Returns: `{ "ok": true, "envelope": {...} }`

- **POST `/api/contracting/{caseId}/esign/webhook`**
  - Webhook endpoint for e-signature events
  - Body: E-signature webhook payload

### Profile (`/api/profile` and `/api`)

- **GET `/api/profile`**

  - Get current user profile
  - Returns: User profile object

- **PUT `/api/profile`**

  - Update user profile
  - Body: Partial profile object
  - Returns: Updated profile

- **GET `/api/user-profiles/{userSub}`**

  - Get user profile by sub
  - Returns: User profile object

- **PUT `/api/user-profiles/{userSub}`**
  - Update user profile by sub (admin)
  - Body: Partial profile object
  - Returns: Updated profile

### Slack Integration (`/api/integrations`)

- **POST `/api/integrations/slack/events`**

  - Slack Events API webhook
  - Handles: `app_mention`, `message`, `reaction_added`, etc.

- **POST `/api/integrations/slack/commands`**

  - Slack Slash Commands endpoint
  - Command: `/polaris <subcommand>`
  - See [Slack Integration](#slack-integration) section for commands

- **POST `/api/integrations/slack/interactive`**

  - Slack Interactive Components (buttons, modals, shortcuts)
  - Handles button clicks, modal submissions, shortcuts

- **POST `/api/integrations/slack/workflows`**
  - Slack Workflow Builder step execution
  - Handles workflow step executions

### Other Endpoints

- **GET `/`** (Health Check)

  - Health check endpoint
  - Returns: `{ "message": "...", "version": "...", "status": "running", ... }`

- **GET `/api/finder/**`\*\*

  - Finder/search endpoints (if implemented)

- **GET `/api/northstar/audit/**`\*\*
  - NorthStar audit endpoints

---

## Slack Integration

The backend provides comprehensive Slack integration through a Slack bot that handles commands, events, and AI-powered interactions.

### Slack Commands

All commands use the `/polaris` slash command:

- **`/polaris help`** - Show help with all available commands
- **`/polaris ask <question>`** - Ask Polaris about RFPs/proposals/tasks/content
- **`/polaris link`** - Link Slack user to Polaris profile
- **`/polaris link-thread <rfpId>`** - Bind next @mention in thread to RFP
- **`/polaris where`** - Show thread binding help
- **`/polaris remember <note>`** - Save personal note/preference (asks for confirmation)
- **`/polaris forget memory`** - Clear saved memory (asks for confirmation)
- **`/polaris recent [n]`** - List latest RFPs (default 10)
- **`/polaris search <keywords>`** - Search RFPs by title/client/type
- **`/polaris upload [n]`** - Upload latest PDFs from channel (default 1, max 5)
- **`/polaris channel`** - Show channel ID (for private rfp-machine config)
- **`/polaris slacktest`** - Post diagnostic message to rfp-machine
- **`/polaris due [days]`** - Show RFPs with submission deadlines due soon (default 7 days)
- **`/polaris pipeline [stage]`** - Group RFPs by workflow stage
- **`/polaris proposals [n]`** - List latest proposals
- **`/polaris proposal <keywords>`** - Search proposals
- **`/polaris summarize <keywords>`** - Get RFP summary + links
- **`/polaris links`** - Show quick links to platform
- **`/polaris rfp <rfpId>`** - Get link to RFP
- **`/polaris open <keywords>`** - Open first search result
- **`/polaris job <jobId>`** - Get RFP upload job status

### Slack Events

The bot handles the following Slack Events API events:

- **`app_mention`** - Bot mentions trigger operator agent
- **`message`** - Thread messages in bound threads trigger operator agent
- **`reaction_added`** - Reactions can trigger workflows
- **Other events** - Additional event types as configured

### Slack Interactive Components

- **Buttons** - Action buttons in messages (approve/reject actions, etc.)
- **Modals** - Interactive modal dialogs for complex inputs
- **Shortcuts** - Global and message shortcuts
- **Workflows** - Slack Workflow Builder integration

### Slack Operator Agent

The Slack Operator Agent (`slack_operator_agent.py`) is an AI-powered agent that handles RFP-related operations in Slack:

**Capabilities:**

- Reads and responds to @mentions and thread messages
- Loads RFP context (OpportunityState, journal, events)
- Updates RFP state based on conversations
- Schedules async jobs for long-running operations
- Proposes actions requiring user approval
- Posts summaries to Slack threads
- Maintains conversation context and memory

**Key Features:**

- **Thread Binding**: Links Slack threads to RFPs for context
- **Opportunity State**: Maintains durable state for each RFP (OpportunityState artifact)
- **Journal Entries**: Records decision narratives
- **Event Logging**: Logs tool calls and decisions
- **Action Proposals**: Gate-keeps destructive operations behind approval
- **Job Scheduling**: Schedules background jobs with `dueAt` timestamps

**Tool Categories Available:**

- RFP/Proposal browsing (list_rfps, get_rfp, list_proposals, etc.)
- Opportunity state management (opportunity_load, opportunity_patch, journal_append, event_append)
- Slack operations (slack_get_thread, slack_post_summary, slack_ask_clarifying_question)
- Agent jobs (schedule_job, agent_job_list, agent_job_get, job_plan)
- Infrastructure/AWS tools (dynamodb*\*, s3*\_, telemetry\__, logs*\*, ecs*_, github\_\_, browser\_\*)
- Action proposals (propose_action)

### Slack Conversational Agent

The Slack Conversational Agent (`slack_agent.py`) handles general Q&A:

**Capabilities:**

- Answers questions about RFPs, proposals, tasks, content
- Provides information without modifying state
- Uses read-only tools and memory

---

## AI Agent System

The backend implements a sophisticated AI agent system with multiple agent types, memory management, context building, and tool execution.

### Agent Architecture

#### Base Agent Interface

All agents implement the `AgentInterface` which provides:

- Memory integration
- Tool registry access
- Context building
- Execution framework

#### Agent Types

1. **Slack Operator Agent** (`slack_operator_agent.py`)

   - Handles RFP operations in Slack
   - Can modify RFP state, schedule jobs, propose actions
   - Full access to all tools

2. **Slack Conversational Agent** (`slack_agent.py`)

   - General Q&A in Slack
   - Read-only access to tools
   - No state modification

3. **User Agent** (`agents/user/user_agent.py`)

   - Handles user requests via API
   - Full tool access

4. **Tool Agent** (`agents/tools/tool_agent.py`)
   - Specialized for tool execution
   - Can discover and execute tools

#### Agent Registry

The `AgentRegistry` (`agents/orchestrators/agent_registry.py`) manages all agents:

- Registers agents and their capabilities
- Routes requests to appropriate agents
- Provides capability discovery

### Memory System

The agent memory system (`memory/`) provides structured memory storage:

#### Memory Types

1. **Episodic Memory**

   - Specific conversations, decisions, outcomes
   - Linked to users, RFPs, Slack threads

2. **Semantic Memory**

   - User preferences, working patterns, domain knowledge
   - Searchable semantic knowledge

3. **Procedural Memory**

   - Successful workflows, tool usage patterns
   - Learning from completed jobs

4. **Collaboration Context Memory**

   - Multi-user collaboration patterns
   - Team decision-making processes

5. **Temporal Event Memory**
   - Deadlines, meetings, milestones
   - Time-based reminders

#### Memory Operations

- **Store**: Save memory with context
- **Retrieve**: Semantic search for relevant memories
- **Update**: Modify existing memories
- **Compress**: Summarize old memories to save space

### Context Building

The context builder (`agent_context_builder.py`) assembles rich context for agents:

**Context Layers:**

1. User profile (preferences, memory, resume, team linkage)
2. Thread conversation history (last 100 messages)
3. RFP state (OpportunityState, journal entries, events)
4. Related RFPs (similar clients, project types)
5. Recent agent jobs for RFP
6. Cross-thread context (other threads mentioning same RFP)

**Features:**

- Smart context prioritization
- Automatic summarization for long contexts
- Context length limits (50K chars max)
- Intelligent truncation

### Tool System

Agents have access to a comprehensive tool registry:

#### Tool Categories

1. **RFP/Proposal Tools**

   - `list_rfps`, `search_rfps`, `get_rfp`
   - `list_proposals`, `get_proposal`
   - `list_tasks`

2. **Opportunity State Tools**

   - `opportunity_load` - Load state + journal + events
   - `opportunity_patch` - Update durable state
   - `journal_append` - Add journal entry
   - `event_append` - Log event

3. **Slack Tools**

   - `slack_get_thread` - Fetch conversation history
   - `slack_list_recent_messages` - List channel messages
   - `slack_post_summary` - Post summary to thread
   - `slack_ask_clarifying_question` - Ask blocking question
   - `slack_send_dm` - Send direct message

4. **Agent Jobs**

   - `schedule_job` - Schedule async job (dueAt ISO time)
   - `agent_job_list` - List jobs with filtering
   - `agent_job_get` - Get job details
   - `agent_job_query_due` - Query due/overdue jobs
   - `job_plan` - Plan job execution

5. **Infrastructure/AWS Tools**

   - `dynamodb_*` - DynamoDB operations
   - `s3_*` - S3 operations
   - `telemetry_*` - CloudWatch Logs Insights
   - `logs_discover_for_ecs` - Discover log groups
   - `ecs_metadata_introspect` - Self-discover ECS info
   - `infrastructure_config_summary` - Get infrastructure config
   - `github_*` - GitHub API operations
   - `aws_ecs_*` - ECS operations
   - `browser_*` - Browser automation (Playwright)

6. **Action Proposal**
   - `propose_action` - Propose action for approval

### Capability Introspection

Agents can discover capabilities dynamically:

- **`list_capabilities`** - List all available capabilities
- **`introspect_capability`** - Get full details about a capability
- **`search_capabilities`** - Search capabilities by query
- **`get_capability_categories`** - Get capability categories

This enables agents to discover new tools and capabilities without hardcoded prompts.

### Agent Jobs System

The agent jobs system enables long-running, asynchronous operations:

#### Job Types

**RFP/Opportunity Management:**

- `opportunity_maintenance` / `perch_refresh` - Sync RFP state from platform
- `opportunity_compact` / `memory_compact` - Compact journal entries

**Agent Operations:**

- `agent_daily_digest` - Generate and send daily Slack reports
- `agent_perch_time` / `telemetry_self_improve` - Self-improvement/analysis tasks

**Notifications:**

- `slack_nudge` - Send Slack notification

**Self-Modification Pipeline:**

- `self_modify_open_pr` - Open GitHub PR for change proposal
- `self_modify_check_pr` - Check GitHub PR status
- `self_modify_verify_ecs` - Verify ECS deployment

**AI Agent Workloads:**

- `ai_agent_ask` - Run AI agent question workload
- `ai_agent_analyze_rfps` - Deep analysis across multiple RFPs (checkpointed)
- `ai_agent_monitor_conditions` - Monitor conditions and take action
- `ai_agent_solve_problem` - Multi-step problem resolution
- `ai_agent_maintain_data` - Data cleanup and sync
- `ai_agent_execute` - Universal job executor (handles any user request)

**Job Execution:**

- Jobs are queued with `dueAt` ISO timestamp
- Executed by NorthStar Job Runner (ECS task running every 4 hours)
- Supports checkpointing for long-running jobs
- Jobs can be scoped to RFPs or be global

### Resilience & Error Handling

The resilience module (`agent_resilience.py`) provides:

- Error classification (transient, permanent, rate_limit, timeout, etc.)
- Exponential backoff with jitter
- Retry with classification
- Graceful degradation
- Partial success handling
- Adaptive timeouts

### Checkpoint System

Long-running operations use checkpoints (`agent_checkpoint.py`):

- Automatic checkpointing (every 10 steps or 5 minutes)
- Manual checkpointing for critical points
- Resume from checkpoints across job runner cycles
- Checkpoints stored as AgentEvents

### Self-Modification Pipeline

Agents can propose code changes via the self-modification pipeline:

- Create change proposals
- Open GitHub PRs
- Check PR status
- Verify ECS deployments

---

## Architecture

### Technology Stack

- **Framework**: FastAPI (Python)
- **Database**: DynamoDB
- **Storage**: S3
- **Queue**: SQS
- **Auth**: AWS Cognito
- **AI**: OpenAI API (GPT models)
- **Observability**: CloudWatch Logs, OpenTelemetry

### Key Services

1. **Backend API Service** (`polaris-backend-production`)

   - FastAPI HTTP API
   - Handles synchronous requests
   - Background tasks for async work

2. **Contracting Worker Service** (`polaris-contracting-worker-production`)

   - SQS queue processor
   - Long-running document generation
   - Runs in separate ECS service

3. **NorthStar Job Runner** (`northstar-job-runner-production`)
   - Scheduled task executor (runs every 4 hours)
   - Executes agent jobs
   - Handles checkpointed long-running operations

### Middleware Stack

1. **RequestContextMiddleware** (outermost) - Adds request-id
2. **CORSMiddleware** - Handles CORS
3. **AccessLogMiddleware** - Structured JSON logging
4. **PortalRateLimitMiddleware** - Rate limiting for portal endpoints
5. **AuthMiddleware** (innermost) - JWT validation

### Error Handling

- RFC 7807 Problem Details format
- Structured error responses
- Exception handlers for DynamoDB errors, validation errors, HTTP exceptions
- Unhandled exception logging to CloudWatch

### Data Models

**RFP (Request for Proposal)**

- Core RFP data (title, client, project type, deadlines)
- Extracted text and analysis
- Review decisions (bid/no-bid)
- Attachments
- Buyer profiles

**Proposal**

- Linked to RFP
- Sections with content
- Generation status
- Review scores and decisions

**OpportunityState**

- Durable state artifact for RFP
- Maintained by operator agent
- Includes stage, due dates, proposal IDs

**Agent Jobs**

- Async job records
- Status tracking (queued, running, completed, failed)
- Checkpoint support
- Result storage

---

## Additional Resources

- See `backend/docs/` for detailed documentation on specific features
- See `README.md` for overall architecture overview
- See individual service files for implementation details
