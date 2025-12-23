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
   - Maintains list of available scrapers
   - Provides metadata about each source
   - Factory method to create scraper instances

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

To add a scraper for a new source:

1. **Create scraper class** in `services/rfp_scrapers/`:

```python
from ..rfp_scraper_base import BaseRfpScraper, RfpScrapedCandidate

class MySourceScraper(BaseRfpScraper):
    def __init__(self):
        super().__init__(
            source_name="mysource",
            base_url="https://example.com/rfps",
        )

    def get_search_url(self, search_params: dict[str, Any] | None = None) -> str:
        # Build search URL based on params
        return f"{self.base_url}?q={search_params.get('query', '')}"

    def _wait_for_listing_content(self) -> None:
        # Wait for listings to load
        self.wait_for_selector(".rfp-listings", timeout_ms=30000)

    def scrape_listing_page(self, search_params: dict[str, Any] | None = None) -> list[RfpScrapedCandidate]:
        candidates = []
        
        # Extract listing items (adjust selectors based on actual page structure)
        # This is a simplified example
        html = self.extract_html(".rfp-listing-item")
        # Parse HTML and extract title, URL, etc.
        
        # For each listing:
        title = self.extract_text(".rfp-title")
        detail_url = self.extract_attribute(".rfp-link", "href")
        
        candidate = self.create_candidate(
            title=title,
            detail_url=detail_url,
            metadata={"extracted_field": "value"},
        )
        candidates.append(candidate)
        
        return candidates
```

2. **Register scraper** in `scraper_registry.py`:

```python
from .my_source_scraper import MySourceScraper

_SCRAPERS = {
    "mysource": MySourceScraper,
    # ... existing scrapers
}

_SOURCE_METADATA = {
    "mysource": {
        "name": "My Source",
        "description": "Description of the source",
        "baseUrl": "https://example.com/rfps",
        "requiresAuth": False,
    },
    # ... existing metadata
}
```

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

