"""
Autonomous memory decision making.

Enables agents to autonomously decide what to remember without explicit tool calls.
Uses lightweight LLM classification to determine if interactions should be stored.
"""

from __future__ import annotations

import json
from typing import Any

from ..ai.verified_calls import call_text_verified
from ..observability.logging import get_logger

log = get_logger("agent_memory_autonomous")


def should_store_memory_autonomous(
    *,
    user_message: str,
    agent_response: str,
    context: dict[str, Any],
    user_sub: str,
) -> dict[str, Any] | None:
    """
    Use lightweight LLM call to determine if interaction should be stored in memory.
    
    Returns decision dict with memoryType, content, isUpdate, etc. if should store,
    None otherwise.
    
    Args:
        user_message: What the user asked/said
        agent_response: What the agent responded/did
        context: Additional context (channel, thread, tools used, etc.)
        user_sub: User identifier
    
    Returns:
        Decision dict with:
        - shouldStore: bool
        - memoryType: str (EPISODIC, SEMANTIC, PROCEDURAL, or NONE)
        - content: str (key information to remember)
        - isUpdate: bool (whether this updates existing knowledge)
        - updateMemoryId: str | None (memory ID if updating)
        - key: str | None (key name if SEMANTIC)
        - value: Any | None (value if SEMANTIC)
        Or None if should not store
    """
    try:
        # Build prompt for LLM classification
        context_str = json.dumps(context, indent=2) if context else "{}"
        
        prompt = f"""Analyze this interaction and determine if it should be stored in memory.

User: {user_message}
Agent: {agent_response}
Context: {context_str}

Determine:
1. Should this be stored? (yes/no)
2. If yes, what type? (EPISODIC, SEMANTIC, PROCEDURAL, or NONE)
3. What is the key information to remember? (extract)
4. Is this updating existing knowledge? (yes/no + which memory if known)

Respond in JSON format:
{{
    "shouldStore": true/false,
    "memoryType": "EPISODIC|SEMANTIC|PROCEDURAL|NONE",
    "content": "key information to remember",
    "isUpdate": true/false,
    "updateMemoryId": "memory_id if updating, null otherwise",
    "key": "key name if SEMANTIC, null otherwise",
    "value": "value if SEMANTIC, null otherwise"
}}"""

        response, _ = call_text_verified(
            purpose="memory_decision",
            messages=[
                {
                    "role": "system",
                    "content": "You are a memory management assistant. Analyze interactions and determine if they should be stored in memory. Be selective - only store meaningful information.",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=500,
            temperature=0.2,
            timeout_s=10,
            retries=1,
        )
        
        # Parse JSON response
        try:
            decision = json.loads(response.strip())
            
            # Validate decision structure
            if not isinstance(decision, dict):
                return None
            
            should_store = decision.get("shouldStore", False)
            if not should_store:
                return None
            
            memory_type = decision.get("memoryType", "").upper()
            if memory_type not in ["EPISODIC", "SEMANTIC", "PROCEDURAL"]:
                return None
            
            # If isUpdate is True, try to find similar existing memories
            is_update = decision.get("isUpdate", False)
            update_memory_id = decision.get("updateMemoryId")
            
            if is_update and not update_memory_id:
                # Try to find similar memories using convenience function
                content = decision.get("content", "")
                if content:
                    from .agent_memory import find_memory_to_update
                    
                    existing_mem = find_memory_to_update(
                        user_sub=user_sub,
                        content=content,
                        memory_type=memory_type,
                        similarity_threshold=0.6,  # Higher threshold for updates
                    )
                    if existing_mem:
                        update_memory_id = existing_mem.get("memoryId")
                        decision["updateMemoryId"] = update_memory_id
                        
                        # Also add scope/type/created_at to decision for easier updating
                        decision["updateMemoryType"] = existing_mem.get("memoryType", "")
                        decision["updateScopeId"] = existing_mem.get("scopeId", "")
                        decision["updateCreatedAt"] = existing_mem.get("createdAt", "")
            
            return decision
            
        except json.JSONDecodeError:
            log.warning("autonomous_memory_decision_parse_failed", response=response[:200])
            return None
            
    except Exception as e:
        log.warning("autonomous_memory_decision_failed", error=str(e))
        return None
