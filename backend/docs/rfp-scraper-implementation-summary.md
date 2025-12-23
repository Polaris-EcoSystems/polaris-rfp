# RFP Scraper System - Implementation Summary

## Overview

A complete scraper system has been implemented to discover and import RFPs from various sources using Playwright browser automation. The system is designed to be extensible, allowing easy addition of new scrapers for different RFP sources.

## Files Created

### Core Scraper Infrastructure

1. **`app/services/rfp_scraper_base.py`**
   - `BaseRfpScraper`: Abstract base class for all scrapers
   - `RfpScrapedCandidate`: Data class for scraped RFP candidates
   - Provides Playwright integration via browser_worker_client
   - Helper methods: navigate, extract_text, extract_html, extract_attribute, create_candidate

2. **`app/services/rfp_scrapers/__init__.py`**
   - Package initialization

3. **`app/services/rfp_scrapers/base_scraper.py`**
   - Re-exports from parent module for convenience

4. **`app/services/rfp_scrapers/scraper_registry.py`**
   - Registry of available scrapers
   - Source metadata (name, description, URLs, auth requirements)
   - Factory methods: get_scraper(), get_available_sources(), is_source_available()

5. **`app/services/rfp_scrapers/planning_org_scraper.py`**
   - Example implementation for American Planning Association
   - Template for creating new scrapers

### Data Layer

6. **`app/repositories/rfp/scraped_rfps_repo.py`**
   - CRUD operations for scraped RFP candidates
   - Functions: create_scraped_rfp(), get_scraped_rfp_by_id(), list_scraped_rfps(), update_scraped_rfp(), mark_scraped_rfp_imported()
   - DynamoDB schema with GSI1 for source-based queries

7. **`app/services/rfp_scraper_jobs_repo.py`**
   - Job management for scraper executions
   - Functions: create_job(), get_job(), update_job(), list_jobs()
   - Tracks job status, candidates found/imported, errors
   - DynamoDB schema with GSI1 for source-based queries

### API Layer

8. **`app/routers/rfp.py` (updated)**
   - New endpoints added:
     - `GET /rfp/scrapers/sources` - List available sources
     - `POST /rfp/scrapers/run` - Trigger a scrape job
     - `GET /rfp/scrapers/jobs` - List scraper jobs
     - `GET /rfp/scrapers/jobs/{jobId}` - Get job details
     - `GET /rfp/scrapers/candidates` - List scraped candidates
     - `GET /rfp/scrapers/candidates/{candidateId}` - Get candidate details
     - `POST /rfp/scrapers/candidates/{candidateId}/import` - Import candidate as RFP
   - Background task: `_process_scraper_job()` - Executes scrapers and saves candidates

### Documentation

9. **`docs/rfp-scraper-system.md`**
   - Complete system documentation
   - Architecture overview
   - Data flow diagrams
   - Guide for creating new scrapers
   - API usage examples

## Key Features

### 1. Extensible Scraper Architecture
- Base class provides common Playwright operations
- Each scraper implements site-specific extraction logic
- Registry pattern for easy addition of new sources

### 2. Candidate Management
- Store scraped RFPs before importing
- Review candidates before committing to full RFP records
- Track import status and link candidates to created RFPs

### 3. Job Tracking
- Track scraper job execution
- Monitor candidates found vs. imported
- Error handling and logging

### 4. Integration with Existing System
- Uses existing `analyze_rfp()` for RFP analysis
- Uses existing `create_rfp_from_analysis()` for RFP creation
- Leverages existing browser_worker infrastructure
- Follows existing repository patterns

## Data Structures

### ScrapedRfp (DynamoDB)
```
pk: SCRAPEDRFP#{candidateId}
sk: CANDIDATE
candidateId: string
source: string (e.g., "planning.org")
sourceUrl: string
title: string
detailUrl: string
status: "pending" | "imported" | "skipped" | "failed"
importedRfpId: string | null
metadata: object
createdAt: ISO timestamp
updatedAt: ISO timestamp
gsi1pk: SCRAPEDRFP_SOURCE#{source}
gsi1sk: {createdAt}#{candidateId}
```

### ScraperJob (DynamoDB)
```
pk: SCRAPERJOB#{jobId}
sk: PROFILE
jobId: string
source: string
searchParams: object
status: "queued" | "running" | "completed" | "failed"
userSub: string | null
candidatesFound: number
candidatesImported: number
error: string | null
createdAt: ISO timestamp
updatedAt: ISO timestamp
startedAt: ISO timestamp | null
finishedAt: ISO timestamp | null
gsi1pk: SCRAPERJOB_SOURCE#{source}
gsi1sk: {createdAt}#{jobId}
```

## Supported Sources (Registry)

Currently registered sources (most are placeholders for future implementation):

1. **planning.org** ✅ Available
   - American Planning Association
   - Basic scraper implemented (needs completion)

2. **linkedin** ⏳ Not implemented
   - Requires authentication

3. **google** ⏳ Not implemented
   - Search-based scraping

4. **bidnetdirect** ⏳ Not implemented
   - Requires authentication

5. **f6s** ⏳ Not implemented

6. **opengov** ⏳ Not implemented
   - Requires authentication

7. **techwerx** ⏳ Not implemented

8. **energywerx** ⏳ Not implemented

9. **herox** ⏳ Not implemented

## Next Steps

### Immediate
1. Complete the planning.org scraper implementation
   - Inspect actual page structure
   - Implement proper selectors for listings
   - Extract title, URL, and metadata

2. Test the system end-to-end
   - Test scraper execution
   - Test candidate import
   - Verify database operations

### Short-term
3. Implement additional scrapers
   - Start with simpler sources (f6s, herox)
   - Add auth support for sources that require it

4. Add frontend integration
   - Update finder page to show scraper sources
   - Add UI for triggering scrapes
   - Add candidate review interface

5. Add pagination support
   - Handle multi-page listings
   - Add pagination to candidate listing endpoint

### Long-term
6. Scheduling/Automation
   - Add scheduled scraping jobs
   - Email/Slack notifications for new candidates

7. Deduplication
   - Prevent importing same RFP twice
   - Cross-reference with existing RFPs

8. Bulk Operations
   - Bulk import multiple candidates
   - Bulk skip/reject candidates

## Usage Example

```python
# Trigger a scrape job
POST /rfp/scrapers/run
{
  "source": "planning.org",
  "searchParams": {"keyword": "solar"}
}

# List scraped candidates
GET /rfp/scrapers/candidates?source=planning.org&status=pending

# Import a candidate as RFP
POST /rfp/scrapers/candidates/{candidateId}/import
```

## Integration Points

The scraper system integrates with:

1. **Browser Worker** (`browser_worker_client.py`)
   - Uses Playwright for page navigation and extraction
   - Requires `BROWSER_WORKER_URL` to be configured

2. **RFP Analyzer** (`rfp_analyzer.py`)
   - Uses `analyze_rfp()` to analyze candidate URLs
   - Extracts RFP data using AI and heuristics

3. **RFP Repository** (`rfps_repo.py`)
   - Uses `create_rfp_from_analysis()` to create RFPs
   - Automatically sets up Google Drive folders

4. **DynamoDB** (`db/dynamodb/table.py`)
   - Uses main table for storage
   - Leverages GSI1 for source-based queries

## Error Handling

- Scraper failures are logged and job status set to "failed"
- Individual candidate save failures are logged but don't fail entire job
- Import failures return proper HTTP errors
- All database operations use try/except for graceful degradation

## Security Considerations

- Browser worker uses allowlist for domains (configured via `agent_allowed_browser_domains`)
- User authentication required for triggering scrapes (via request.state.user)
- Scraped data is stored with user attribution (userSub on jobs)

