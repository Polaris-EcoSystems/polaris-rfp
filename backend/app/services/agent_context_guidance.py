"""
Context guidance and best practices for prompt construction.

This module provides guidance on how to structure prompts and context
for optimal AI agent performance.
"""

CONTEXT_GUIDANCE = """
Context Organization Best Practices:

1. PRIORITY ORDER (Most Important First):
   - User identity and preferences (who they are, what they like)
   - Current conversation thread (immediate context)
   - Relevant memories (what happened before)
   - Current task/RFP state (what we're working on)
   - Related items (similar RFPs, related tasks)
   - Historical context (older jobs, cross-thread context)

2. CONTEXT SECTIONS:
   Use clear section headers to help the agent navigate context:
   - === USER_IDENTITY ===
   - === CONVERSATION_HISTORY ===
   - === RELEVANT_MEMORIES ===
   - === RFP_STATE ===
   - === RELATED_RFPS ===

3. QUERY-AWARE RETRIEVAL:
   - When user asks a question, extract keywords from the question
   - Use those keywords to search for relevant memories and context
   - Prioritize context that matches query keywords
   - This ensures the agent gets context most relevant to answering the question

4. CONTEXT LENGTH MANAGEMENT:
   - Always preserve user identity (highest priority)
   - Preserve recent conversation (essential for continuity)
   - Truncate older/less relevant context when needed
   - Use summaries for very old context
   - Include metadata about what was truncated

5. TEMPORAL RELEVANCE:
   - Recent context is usually more relevant than old context
   - Prioritize context from the current thread/conversation
   - Use timestamps to help agent understand context age
   - Compress or summarize very old context

6. STRUCTURED DATA:
   - Format lists, dates, and structured data clearly
   - Use consistent formatting for IDs, URLs, timestamps
   - Include data types and units where relevant
   - Make relationships between entities explicit

7. PROVENANCE AND SOURCES:
   - Include where context came from (source metadata)
   - Include confidence/relevance scores when available
   - Help agent understand context reliability
   - Distinguish between authoritative vs. inferred context
"""
