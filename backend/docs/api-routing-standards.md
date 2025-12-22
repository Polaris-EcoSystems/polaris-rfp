# API Routing Standards

This document outlines the standards for API routing in the Polaris RFP backend and frontend.

## Backend Route Standards

### Trailing Slash Support

Since FastAPI is configured with `redirect_slashes=False` (to avoid redirect loops through the Next.js proxy), **all routes must explicitly support both with and without trailing slashes**.

#### Pattern for Routes Without Path Parameters

For routes like `/status`, `/jobs`, `/activity`, etc.:

```python
@router.get("/status")
def get_status(request: Request) -> dict[str, Any]:
    """Get status (no trailing slash)."""
    return _get_status_impl(request)


@router.get("/status/")
def get_status_slash(request: Request) -> dict[str, Any]:
    """Get status (with trailing slash)."""
    return _get_status_impl(request)


def _get_status_impl(request: Request) -> dict[str, Any]:
    """Implementation function."""
    # Actual logic here
    return {"ok": True}
```

#### Pattern for Routes With Path Parameters

For routes like `/jobs/{job_id}`, trailing slash support is optional but recommended for consistency:

```python
@router.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    """Get job (no trailing slash)."""
    return _get_job_impl(job_id)


@router.get("/jobs/{job_id}/", include_in_schema=False)
def get_job_slash(job_id: str) -> dict[str, Any]:
    """Get job (with trailing slash)."""
    return _get_job_impl(job_id)


def _get_job_impl(job_id: str) -> dict[str, Any]:
    """Implementation function."""
    # Actual logic here
    return {"ok": True, "job": {...}}
```

### Route Naming Conventions

- Use kebab-case for route paths: `/api/agents/jobs`, `/api/integrations/status`
- Use descriptive names: `/api/rfp/{id}/drive-folder` not `/api/rfp/{id}/folder`
- Group related routes under common prefixes: `/api/agents/*`, `/api/integrations/*`

### HTTP Method Usage

- `GET`: Read operations (list, get, status checks)
- `POST`: Create operations, actions that modify state
- `PUT`: Full updates (replace entire resource)
- `PATCH`: Partial updates (update specific fields)
- `DELETE`: Delete operations

## Frontend API Call Standards

### Path Format

**Use trailing slashes ONLY for list routes (root routes)**. All other routes should NOT have trailing slashes:

```typescript
// ✅ Correct - List routes (root routes) use trailing slashes
api.get(proxyUrl('/api/rfp/'))
api.get(proxyUrl('/api/templates/'))
api.get(proxyUrl('/api/proposals/'))
api.get(proxyUrl('/api/contract-templates/'))

// ✅ Correct - Other routes do NOT use trailing slashes
api.get(proxyUrl('/api/agents/jobs'))
api.get(proxyUrl('/api/integrations/status'))
api.get(proxyUrl(`/api/rfp/${cleanPathToken(id)}`))
api.get(proxyUrl(`/api/agents/jobs/${cleanPathToken(jobId)}`))

// ❌ Incorrect - Don't mix patterns
api.get(proxyUrl('/api/agents/jobs/')) // Should be without trailing slash
api.get(proxyUrl('/api/rfp')) // Should be with trailing slash (list route)
```

### Using proxyUrl()

All API calls must use the `proxyUrl()` helper function:

```typescript
import { proxyUrl } from '@/lib/api'

// ✅ Correct
api.get(proxyUrl('/api/agents/jobs'), { params })

// ❌ Incorrect
api.get('/api/agents/jobs', { params })
```

### Path Parameters

Use `cleanPathToken()` for path parameters to prevent injection:

```typescript
import { cleanPathToken } from '@/lib/api'

// ✅ Correct
api.get(proxyUrl(`/api/agents/jobs/${cleanPathToken(jobId)}`))

// ❌ Incorrect
api.get(proxyUrl(`/api/agents/jobs/${jobId}`))
```

## Current Implementation Status

### Routers with Full Trailing Slash Support

- ✅ `backend/app/routers/agents.py` - All routes support both versions

  - `/infrastructure` and `/infrastructure/`
  - `/jobs` and `/jobs/`
  - `/activity` and `/activity/`
  - `/metrics` and `/metrics/`
  - `/diagnostics` and `/diagnostics/`
  - `/workers` and `/workers/`

- ✅ `backend/app/routers/integrations.py` - All routes support both versions

  - `/status` and `/status/`
  - `/activities` and `/activities/`

- ✅ `backend/app/routers/integrations_canva.py` - Key routes support both versions

  - `/status` and `/status/`
  - `/company-mappings` and `/company-mappings/`

- ✅ `backend/app/routers/rfp.py` - Many routes support both versions
  - `/{id}` and `/{id}/`
  - `/{id}/drive-folder` and `/{id}/drive-folder/`
  - And others

### List Routes (Root Routes)

These routes use `@router.get("/")` which naturally requires trailing slashes:

- `/api/rfp/` - List RFPs
- `/api/templates/` - List templates
- `/api/proposals/` - List proposals
- `/api/contract-templates/` - List contract templates

These are correctly called with trailing slashes in the frontend.

### Routers Needing Updates

Other routers should be updated to follow the same pattern as routes are added or modified.

## Testing

When adding new routes:

1. Test both with and without trailing slashes
2. Ensure the route works through the Next.js proxy
3. Verify path parameters are properly sanitized
4. Check that query parameters work correctly

## Examples

### Complete Example: Agents Router

```python
@router.get("/jobs")
def list_jobs(request: Request, limit: int = 50) -> dict[str, Any]:
    """List jobs (no trailing slash)."""
    return _list_jobs_impl(request, limit)


@router.get("/jobs/")
def list_jobs_slash(request: Request, limit: int = 50) -> dict[str, Any]:
    """List jobs (with trailing slash)."""
    return _list_jobs_impl(request, limit)


def _list_jobs_impl(request: Request, limit: int = 50) -> dict[str, Any]:
    """Implementation."""
    lim = max(1, min(100, int(limit or 50)))
    jobs = list_recent_jobs(limit=lim)
    return {"ok": True, "jobs": jobs, "count": len(jobs)}
```

### Complete Example: Frontend API Client

```typescript
export const agentsApi = {
  listJobs: (params?: { limit?: number }) =>
    api.get<{
      ok: boolean
      jobs: AgentJob[]
      count: number
    }>(proxyUrl('/api/agents/jobs'), { params }),

  getJob: (jobId: string) =>
    api.get<{ ok: boolean; job: AgentJob }>(
      proxyUrl(`/api/agents/jobs/${cleanPathToken(jobId)}`),
    ),
}
```
