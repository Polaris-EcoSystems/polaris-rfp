# External Context Integration

## Overview

The agent now has access to real-world external context from various sources, making it aware of current events, weather, research, and geopolitical developments. This prevents the agent from being "stuck in the past" and enables more informed, contextually-aware responses.

## New Memory Type

### EXTERNAL_CONTEXT

A new memory type for storing external/real-world context:

- Business and finance news
- Weather data
- Geopolitical events
- Research papers (academic and financial)

External context is stored at GLOBAL scope with appropriate tags and keywords for retrieval.

## External Data Sources

### 1. Business & Finance News

**Source**: NewsAPI (free tier: 100 requests/day)
**API Key**: `NEWS_API_KEY` environment variable

**Usage**:

- Fetches business/finance news articles
- Supports search queries
- Cached for 1 hour

**Example queries**:

- "federal contracting"
- "government procurement"
- "business news"

### 2. Weather Data

**Source**: OpenWeatherMap API (free tier)
**API Key**: `OPENWEATHER_API_KEY` environment variable

**Usage**:

- Fetches weather for any zip code
- Returns temperature, conditions, humidity, wind speed
- Cached for 15 minutes (weather changes frequently)

**Example**:

- Query: "What's the weather in 90210?"
- Fetches weather for zip code 90210

### 3. Research Papers (arXiv)

**Source**: arXiv API (free, no auth required)

**Usage**:

- Searches academic research papers
- Supports relevance-based and date-based sorting
- Cached for 6 hours (papers don't change frequently)

**Example queries**:

- "government procurement"
- "federal contracting"
- "public sector innovation"

### 4. Financial/Business Research

**Source**: arXiv (enhanced with finance keywords)
**Future**: SSRN integration possible

**Usage**:

- Searches for financial and business research
- Adds finance/economics keywords automatically
- Cached for 1 week (research stays relevant longer)

### 5. Geopolitical Events

**Source**: NewsAPI (filtered for political/government news)
**API Key**: `NEWS_API_KEY` environment variable

**Usage**:

- Fetches recent geopolitical news
- Optional region filtering
- Cached for 1 hour

**Example queries**:

- "United States"
- "Europe"
- "Asia"

## Agent Tools

The agent has access to the following tools for fetching external context:

### `external_news`

Fetch business and finance news.

**Args**:

- `query`: Search query (optional)
- `limit`: Max articles (default: 10, max: 20)

### `external_weather`

Fetch weather data for a zip code.

**Args**:

- `zipCode`: US zip code (required)
- `countryCode`: Country code (default: "US")

### `external_research`

Fetch research papers from arXiv.

**Args**:

- `query`: Search query (required)
- `maxResults`: Max results (default: 10, max: 100)
- `sortBy`: Sort order ("relevance", "lastUpdatedDate", "submittedDate")

### `external_financial_research`

Fetch financial/business research papers.

**Args**:

- `query`: Search query (required)
- `limit`: Max results (default: 10, max: 50)

### `external_geopolitical`

Fetch recent geopolitical events.

**Args**:

- `region`: Optional region filter
- `limit`: Max events (default: 10, max: 20)

### `external_context`

Convenience tool that auto-detects and fetches relevant external context types.

**Args**:

- `query`: User's query (required)
- `contextTypes`: Optional specific types to fetch
- `limitPerType`: Max items per type (default: 5)

## Automatic Context Integration

When a user query is provided to `build_comprehensive_context()`, the system automatically:

1. **Extracts keywords** from the query
2. **Detects relevant context types** based on keywords:
   - Business keywords → news + financial research
   - Weather keywords → weather
   - Political keywords → geopolitical events
   - Research keywords → research + financial research
3. **Fetches relevant context** for detected types
4. **Stores in memory** for future retrieval
5. **Includes in prompt** (formatted and limited to 1500 chars)

## Caching Strategy

External context is cached at multiple levels:

1. **In-memory cache** (short-term, per-process):

   - News: 1 hour
   - Weather: 15 minutes
   - Research: 6 hours
   - Geopolitical: 1 hour

2. **Memory storage** (persistent, DynamoDB):

   - Stored with TTL based on context type
   - Queryable via semantic search
   - Used for context building

3. **Refresh strategy**:
   - Weather refreshed frequently (changes often)
   - News refreshed hourly (sufficient for most use cases)
   - Research cached longer (papers don't change)
   - Geopolitical events refreshed hourly

## Configuration

### Required Environment Variables

```bash
# NewsAPI (business news, geopolitical events)
NEWS_API_KEY=your_newsapi_key

# OpenWeatherMap (weather data)
OPENWEATHER_API_KEY=your_openweather_key
```

### API Keys Setup

1. **NewsAPI**: Get free API key from https://newsapi.org/

   - Free tier: 100 requests/day
   - Good for development and moderate usage

2. **OpenWeatherMap**: Get free API key from https://openweathermap.org/api

   - Free tier: 60 calls/minute
   - Sufficient for most use cases

3. **arXiv**: No API key needed (free public API)

## Usage Examples

### Automatic Context Inclusion

When the agent receives a query like:

- "What's happening in federal contracting this week?"

The system automatically:

1. Detects "federal contracting" as business-related
2. Fetches relevant business news
3. Includes formatted news in context
4. Stores in memory for future queries

### Manual Tool Usage

The agent can also explicitly call tools:

```python
# User asks: "What's the weather in San Francisco?"
# Agent calls: external_weather(zipCode="94102")
```

### Research Queries

```python
# User asks: "Find research on government procurement"
# Agent calls: external_research(query="government procurement")
```

## Memory Storage Format

External context is stored with:

- **Memory Type**: `EXTERNAL_CONTEXT`
- **Scope**: `GLOBAL` (accessible to all users)
- **Tags**: `["external_context", "<context_type>"]`
- **Keywords**: Extracted from query + context-specific keywords
- **Metadata**: Full context data, source, fetched timestamp
- **TTL**: Based on context type (weather: 1 hour, research: 1 week)

## Benefits

1. **Current Awareness**: Agent knows about recent events, not just historical data
2. **Relevant Context**: Query-aware fetching ensures relevant external context
3. **Persistent Storage**: External context stored in memory for reuse
4. **Efficient Caching**: Multiple cache layers prevent API rate limit issues
5. **Flexible Integration**: Can be included automatically or fetched on-demand

## Future Enhancements

Potential improvements:

1. **SSRN Integration**: Financial research from Social Science Research Network
2. **Google Scholar**: Academic paper search
3. **Financial APIs**: Stock prices, economic indicators (Alpha Vantage, etc.)
4. **Government APIs**: Federal procurement data, contract awards
5. **RSS Feeds**: Custom news feeds for specific topics
6. **Twitter/X API**: Social media sentiment and trending topics
7. **Wikipedia API**: Quick factual lookups
8. **Market Data**: Real-time financial market information

## Implementation Files

- `backend/app/services/external_context_fetcher.py`: Core fetching logic
- `backend/app/services/external_context_service.py`: Service layer and formatting
- `backend/app/services/agent_tools/external_context_tools.py`: Agent tools
- `backend/app/services/agent_context_builder.py`: Integration into context building
- `backend/app/services/agent_memory_db.py`: EXTERNAL_CONTEXT memory type
