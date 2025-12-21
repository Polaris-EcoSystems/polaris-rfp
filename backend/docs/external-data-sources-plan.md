# External Data Sources Integration Plan

## Overview

This document outlines the comprehensive plan for integrating real-world external data sources to enhance the agent's contextual awareness and prevent it from being "stuck in the past."

## Implemented Sources (✅)

### 1. Business & Finance News ✅

- **Source**: NewsAPI (free tier)
- **API Key**: `NEWS_API_KEY`
- **Cache**: 1 hour
- **Use Cases**: Current business events, market trends, industry news relevant to RFPs
- **Status**: Fully implemented with agent tools

### 2. Weather Data ✅

- **Source**: OpenWeatherMap (free tier)
- **API Key**: `OPENWEATHER_API_KEY`
- **Cache**: 15 minutes
- **Use Cases**: Weather conditions for project planning, logistics, RFP requirements
- **Status**: Fully implemented with agent tools

### 3. Research Papers (arXiv) ✅

- **Source**: arXiv API (free, no auth)
- **Cache**: 6 hours
- **Use Cases**: Academic research, technical papers, scholarly articles
- **Status**: Fully implemented with XML parsing and agent tools

### 4. Geopolitical Events ✅

- **Source**: NewsAPI (filtered)
- **API Key**: `NEWS_API_KEY`
- **Cache**: 1 hour
- **Use Cases**: Political developments, policy changes, government actions
- **Status**: Fully implemented with agent tools

### 5. Financial/Business Research ✅

- **Source**: arXiv (enhanced with finance keywords)
- **Cache**: 1 week
- **Use Cases**: Financial research, business strategy papers
- **Status**: Implemented, ready for SSRN integration

## Recommended Additional Sources

### 1. Financial Market Data (Recommended)

**Sources**:

- Alpha Vantage API (free tier: 5 API calls/minute, 500 calls/day)
- Yahoo Finance API (free, unofficial)
- IEX Cloud (free tier available)

**Use Cases**:

- Stock prices for companies mentioned in RFPs
- Market trends affecting contract values
- Economic indicators
- Currency exchange rates (for international contracts)

**Implementation Priority**: High (relevant for financial RFPs)

### 2. Government Procurement Data (Recommended)

**Sources**:

- USAspending.gov API (free)
- SAM.gov API (free, requires registration)
- GovTribe API (paid, but comprehensive)

**Use Cases**:

- Historical contract awards
- Agency spending patterns
- Similar contract analysis
- Bid history and outcomes

**Implementation Priority**: Very High (directly relevant to RFP work)

### 3. SSRN (Social Science Research Network) (Recommended)

**Sources**:

- SSRN API (may require access)
- SSRN RSS feeds (free)
- Web scraping (with proper attribution)

**Use Cases**:

- Financial research papers
- Business strategy research
- Economics papers
- More business-focused than arXiv

**Implementation Priority**: Medium (complements arXiv)

### 4. Google Scholar (Recommended)

**Sources**:

- Google Scholar API (limited, may require scraping)
- SerpAPI (paid, wraps Google Scholar)
- Academic search APIs

**Use Cases**:

- Broader academic search
- Citation tracking
- Related paper discovery

**Implementation Priority**: Medium (broader than arXiv)

### 5. Federal Register (Recommended)

**Sources**:

- Federal Register API (free)

**Use Cases**:

- Federal regulations and rules
- Proposed rule changes
- Compliance requirements
- Policy announcements

**Implementation Priority**: High (relevant for federal contracts)

### 6. Economic Indicators (Recommended)

**Sources**:

- FRED (Federal Reserve Economic Data) API (free)
- World Bank API (free)
- IMF Data API (free)

**Use Cases**:

- Economic trends
- GDP, inflation, unemployment data
- Economic context for RFPs

**Implementation Priority**: Medium (useful for economic analysis)

### 7. Company Information (Recommended)

**Sources**:

- Clearbit API (paid, free tier available)
- ZoomInfo API (paid)
- Crunchbase API (paid, free tier limited)
- SEC EDGAR API (free, for public companies)

**Use Cases**:

- Company profiles and information
- Funding history
- Recent news about companies
- Competitor analysis

**Implementation Priority**: Medium (useful for competitive intelligence)

### 8. Social Media Sentiment (Optional)

**Sources**:

- Twitter/X API v2 (paid, limited free tier)
- Reddit API (free)
- News sentiment APIs

**Use Cases**:

- Public sentiment about topics
- Trending discussions
- Social media mentions

**Implementation Priority**: Low (nice to have, but less critical)

### 9. Wikipedia/Wikidata (Recommended)

**Sources**:

- Wikipedia API (free)
- Wikidata API (free)

**Use Cases**:

- Quick factual lookups
- Entity information
- Background knowledge
- Reference data

**Implementation Priority**: Medium (useful for quick context)

### 10. Calendar/Holiday Data (Recommended)

**Sources**:

- Public holidays APIs (free)
- Business calendar APIs

**Use Cases**:

- Deadline calculations
- Business day calculations
- Holiday-aware scheduling

**Implementation Priority**: Low (nice to have)

## Implementation Strategy

### Phase 1: Core External Context (✅ Complete)

- News (NewsAPI)
- Weather (OpenWeatherMap)
- Research (arXiv)
- Geopolitical events

### Phase 2: Procurement & Government Data (High Priority)

1. USAspending.gov API integration
2. SAM.gov data (if API available)
3. Federal Register API

### Phase 3: Financial & Economic Data (Medium Priority)

1. Alpha Vantage for stock/market data
2. FRED API for economic indicators
3. SSRN integration for financial research

### Phase 4: Company & Competitive Intelligence (Medium Priority)

1. SEC EDGAR API
2. Company information APIs
3. Competitive analysis tools

### Phase 5: Enhanced Research (Low Priority)

1. Google Scholar integration
2. Additional academic sources
3. Citation networks

## Architecture Considerations

### Caching Strategy

Different data sources need different cache TTLs:

- **Real-time data** (weather, stock prices): 1-15 minutes
- **News/Events**: 1 hour
- **Research papers**: 6 hours - 1 week
- **Government data**: 1-24 hours (depending on update frequency)
- **Economic indicators**: Daily (updated less frequently)
- **Company data**: 1-24 hours
- **Wikipedia**: 1 week (relatively stable)

### Rate Limiting

Many free APIs have rate limits:

- NewsAPI: 100 requests/day (free tier)
- OpenWeatherMap: 60 calls/minute (free tier)
- Alpha Vantage: 5 calls/minute, 500/day (free tier)
- arXiv: No official limit, but be respectful

**Strategy**:

- Aggressive caching
- Batch requests when possible
- Queue requests if rate limited
- Use paid tiers for production if needed

### Error Handling

All external API calls should:

- Fail gracefully (don't break agent if API is down)
- Log errors for monitoring
- Use cached data when available
- Retry with exponential backoff for transient failures

### Data Storage

External context is stored in:

- **Memory System**: EXTERNAL_CONTEXT memory type
- **Scope**: GLOBAL (accessible to all users)
- **TTL**: Based on data freshness requirements
- **Searchable**: Via semantic search with keywords/tags

### Cost Management

- Monitor API usage and costs
- Use free tiers where possible
- Implement usage limits
- Cache aggressively
- Consider paid tiers only for high-value sources

## Integration Points

### Agent Tools

All external data sources are accessible via agent tools:

- `external_news`: Business/finance news
- `external_weather`: Weather data
- `external_research`: Research papers
- `external_financial_research`: Financial research
- `external_geopolitical`: Geopolitical events
- `external_context`: Auto-detect and fetch relevant context

### Context Building

External context is automatically included in prompts when:

1. User query contains relevant keywords
2. Context types are auto-detected
3. Relevant external context is fetched and formatted
4. Stored in memory for future retrieval

### Memory Integration

External context:

- Stored with EXTERNAL_CONTEXT memory type
- Tagged with context type and keywords
- Queryable via semantic search
- Automatically expires based on TTL
- Included in context building when relevant

## Configuration

### Environment Variables

```bash
# Required for news and geopolitical events
NEWS_API_KEY=your_newsapi_key

# Required for weather
OPENWEATHER_API_KEY=your_openweather_key

# Future additions (when implemented)
ALPHA_VANTAGE_API_KEY=your_alphavantage_key
USA_SPENDING_API_KEY=optional_for_higher_limits
FRED_API_KEY=your_fred_key
```

### API Key Setup

1. **NewsAPI**: https://newsapi.org/register

   - Free tier: 100 requests/day
   - Developer tier: $449/month for higher limits

2. **OpenWeatherMap**: https://openweathermap.org/api

   - Free tier: 60 calls/minute, sufficient for most uses

3. **Alpha Vantage**: https://www.alphavantage.co/support/#api-key

   - Free tier: 5 calls/minute, 500/day
   - Premium: Higher limits available

4. **FRED API**: https://fred.stlouisfed.org/docs/api/api_key.html
   - Free, unlimited for registered users

## Testing Strategy

1. **Unit Tests**: Test each fetcher function with mock responses
2. **Integration Tests**: Test with real APIs (use test keys)
3. **Cache Tests**: Verify caching behavior
4. **Error Handling Tests**: Test graceful degradation
5. **Rate Limit Tests**: Verify rate limiting and queuing

## Monitoring

Track:

- API call counts and costs
- Cache hit rates
- Error rates by source
- Response times
- Data freshness
- Usage patterns

## Future Enhancements

1. **Webhook Integration**: Receive updates from APIs when available
2. **Scheduled Refreshes**: Pre-fetch common queries
3. **Data Summarization**: Use LLM to summarize large datasets
4. **Trend Analysis**: Identify trends in external data
5. **Alert System**: Notify users of relevant external events
6. **Custom Sources**: Allow users to add custom RSS feeds or APIs
