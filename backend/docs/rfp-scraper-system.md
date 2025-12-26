# RFP Scraper System

This document describes the RFP scraper system for automatically discovering RFPs from various sources.

## Overview

The scraper system allows you to:
- Scrape RFP listings from various sources (planning.org, LinkedIn, Google, etc.)
- Store scraped candidates for review
- Import candidates as full RFPs after review
- Track scraper jobs and their results

## Architecture

### Core Components

1. **Base Scraper** (`rfp_scraper_base.py`)
   - Abstract base class for all scrapers
   - Handles Playwright browser automation via browser_worker_client
   - Provides common methods: navigate, extract_text, extract_html, etc.

2. **Scraper Registry** (`rfp_scrapers/scraper_registry.py`)
   - Discovers scraper “source modules” under `rfp_scrapers/sources/`
   - Provides metadata about each source
   - Factory method to create scraper instances via per-source `create()`

3. **Source Modules** (`rfp_scrapers/sources/*.py`)
   - Each source is its own module (LinkedIn, Google, BidNet Direct, etc.)
   - Exposes:
     - `SOURCE`: a manifest dict (id/name/description/baseUrl/authKind/kind/implemented)
     - `create(search_params, ctx)`: factory returning a scraper instance
   - This keeps the backend **extensible**: adding a source is just adding a new module.

3. **Scraped RFPs Repository** (`repositories/rfp/scraped_rfps_repo.py`)
   - Stores scraped RFP candidates before they become full RFPs
   - Tracks status: pending, imported, skipped, failed
   - Links candidates to imported RFPs

4. **Scraper Jobs Repository** (`services/rfp_scraper_jobs_repo.py`)
   - Tracks scraper job execution
   - Stores job status, candidates found, import statistics

5. **API Endpoints** (`routers/rfp.py`)
   - `/rfp/scrapers/sources` - List available sources
   - `/rfp/scrapers/run` - Trigger a scrape job
   - `/rfp/scrapers/jobs` - List scraper jobs
   - `/rfp/scrapers/jobs/{jobId}` - Get job details
   - `/rfp/scrapers/candidates` - List scraped candidates
   - `/rfp/scrapers/candidates/{candidateId}/import` - Import candidate as RFP

## Data Flow

1. **Trigger Scrape**
   ```
   POST /rfp/scrapers/run
   → Creates scraper job (status: queued)
   → Background task starts processing
   ```

2. **Process Scrape**
   ```
   → Creates browser context via browser_worker
   → Navigates to source listing page
   → Extracts RFP candidates
   → Saves candidates to database
   → Updates job status (completed/failed)
   ```

3. **Review Candidates**
   ```
   GET /rfp/scrapers/candidates?source=planning.org
   → List pending candidates
   → User reviews titles, URLs, metadata
   ```

4. **Import Candidate**
   ```
   POST /rfp/scrapers/candidates/{candidateId}/import
   → Analyzes candidate's detail URL using analyze_rfp
   → Creates full RFP via create_rfp_from_analysis
   → Marks candidate as imported
   → Links candidate to created RFP
   ```

## Creating a New Scraper

To add a scraper for a new source (modular “source module” approach):

1. **Create a new source module** in `app/pipeline/search/rfp_scrapers/sources/`:

```python
from __future__ import annotations

from typing import Any

from ..framework import ScraperContext
from ..framework import UnimplementedScraper

SOURCE: dict[str, Any] = {
    "id": "mysource",
    "name": "My Source",
    "description": "Describe the source workflow",
    "baseUrl": "https://example.com/rfps",
    "kind": "browser",          # browser|api|hybrid
    "authKind": "none",         # none|user_session|api_key|...
    "requiresAuth": False,
    "implemented": False,       # flip to True once implemented
}

def create(*, search_params: dict[str, Any] | None, ctx: ScraperContext):
    _ = (search_params, ctx)
    return UnimplementedScraper(source_id="mysource", reason="fill_in_workflow")
```

2. **Implement the scraper** (browser-based scrapers can still use `BaseRfpScraper`)
   - For complex sources (LinkedIn/Google/BidNet/OpenGov), implement a dedicated
     workflow with auth/session management and pagination.
   - When ready, set `SOURCE["implemented"] = True`.

## Example Usage

### List Available Sources

```bash
GET /rfp/scrapers/sources
```

Response:
```json
{
  "ok": true,
  "sources": [
    {
      "id": "planning.org",
      "name": "American Planning Association",
      "description": "Daily RFP/RFQ listings for planning consultants",
      "baseUrl": "https://www.planning.org/consultants/rfp/search/",
      "requiresAuth": false,
      "available": true
    },
    ...
  ]
}
```

### Trigger a Scrape Job

```bash
POST /rfp/scrapers/run
Content-Type: application/json

{
  "source": "planning.org",
  "searchParams": {
    "keyword": "solar"
  }
}
```

Response:
```json
{
  "ok": true,
  "job": {
    "id": "scraperjob_abc123",
    "source": "planning.org",
    "status": "queued",
    "createdAt": "2024-01-01T00:00:00Z"
  }
}
```

### List Scraped Candidates

```bash
GET /rfp/scrapers/candidates?source=planning.org&status=pending
```

Response:
```json
{
  "data": [
    {
      "id": "scraped_xyz789",
      "source": "planning.org",
      "title": "Solar RFP for City Planning",
      "detailUrl": "https://planning.org/rfp/123",
      "status": "pending",
      "scrapedAt": "2024-01-01T00:00:00Z",
      "metadata": {}
    }
  ],
  "nextToken": "...",
  "pagination": {
    "limit": 50,
    "source": "planning.org",
    "status": "pending"
  }
}
```

### Import a Candidate

```bash
POST /rfp/scrapers/candidates/scraped_xyz789/import
```

Response:
```json
{
  "ok": true,
  "rfp": {
    "_id": "rfp_abc123",
    "title": "Solar RFP for City Planning",
    ...
  },
  "candidateId": "scraped_xyz789"
}
```

## Status Values

### Scraper Jobs
- `queued` - Job is waiting to be processed
- `running` - Job is currently running
- `completed` - Job finished successfully
- `failed` - Job encountered an error

### Scraped Candidates
- `pending` - Candidate hasn't been imported yet
- `imported` - Candidate was imported as an RFP
- `skipped` - Candidate was manually skipped
- `failed` - Import attempt failed

## Database Schema

### ScrapedRfp
- `pk`: `SCRAPEDRFP#{candidateId}`
- `sk`: `CANDIDATE`
- `candidateId`: Unique ID
- `source`: Source identifier
- `title`: RFP title
- `detailUrl`: URL to full RFP details
- `status`: pending|imported|skipped|failed
- `importedRfpId`: Link to created RFP (if imported)
- `metadata`: Additional scraped data
- `gsi1pk`: `SCRAPEDRFP_SOURCE#{source}` (for querying by source)
- `gsi1sk`: `{createdAt}#{candidateId}`

### ScraperJob
- `pk`: `SCRAPERJOB#{jobId}`
- `sk`: `PROFILE`
- `jobId`: Unique ID
- `source`: Source identifier
- `status`: queued|running|completed|failed
- `candidatesFound`: Number of candidates found
- `candidatesImported`: Number successfully saved
- `error`: Error message (if failed)
- `gsi1pk`: `SCRAPERJOB_SOURCE#{source}` (for querying by source)
- `gsi1sk`: `{createdAt}#{jobId}`

## Future Enhancements

- Implement scrapers for all listed sources
- Add pagination support for listing pages
- Add scheduling/automated scraping
- Add filtering/searching of candidates
- Add bulk import functionality
- Add webhook notifications for new candidates
- Add candidate deduplication (prevent importing same RFP twice)

## LinkedIn Scraper (Playwright storageState auth)

The `linkedin` source is implemented as a Playwright/browser-worker workflow and **does not use Selenium**.

### Auth model
- The backend expects a Playwright `storageState` (cookies/localStorage) for LinkedIn.
- Upload this via the existing Finder endpoint: `POST /api/finder/linkedin/storage-state`.
- Scraper jobs for `source="linkedin"` run as the authenticated user (job.userSub), and will fail if no storageState exists for that user.

### Required config
- Ensure `AGENT_ALLOWED_BROWSER_DOMAINS` includes `linkedin.com` (and any other domains you want to follow out to).
- Ensure `BROWSER_WORKER_URL` is configured and the browser worker is deployed with the updated `/v1/context` that accepts `storageState`.

### Search params
Provide one of:
- `searchParams.searchUrl`: a full LinkedIn content search URL (recommended)
- `searchParams.query`: keywords (the scraper will build a best-effort search URL)

## Google Search Scraper (Custom Search API)

The `google` source is implemented using **Google Custom Search JSON API** (CSE), not browser automation.

### Required config
- `GOOGLE_CSE_API_KEY`
- `GOOGLE_CSE_CX` (Search engine ID)

If either is missing, the source will show as **unavailable**.

### Search params
- `searchParams.query` (required)
- `searchParams.dateRestrict` (optional): e.g. `d7` for last 7 days
- `searchParams.siteSearch` (optional): restrict to a domain
- `searchParams.maxCandidates` (optional): cap results

