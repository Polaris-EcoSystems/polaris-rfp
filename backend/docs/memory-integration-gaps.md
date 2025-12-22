# Memory Integration Gaps

This document identifies places where the code should query the memory system but currently only checks legacy sources (like `user_profile.aiPreferences` or `user_profile.aiMemorySummary`).

## Fixed

1. ✅ **`slack_agent.py` - `_is_whats_my_preferences()` handler** (line ~501)
   - **Issue**: Only checked `prof.get("aiPreferences")` from user profile
   - **Fix**: Now also queries semantic memories using `get_memories_for_context()` with `memory_types=["SEMANTIC"]`
   - **Status**: Fixed

## Needs Fixing

### 1. `agent_context_builder.py` - `build_user_context()` (lines 35-36, 135-143)

**Location**: `backend/app/services/agent_context_builder.py`

**Issue**:

- Only uses `prof.get("aiPreferences")` for preferences (line 35)
- Only uses `prof.get("aiMemorySummary")` for memory summary (line 36)
- Should also query semantic memories for preferences and episodic memories instead of just `aiMemorySummary`

**Impact**: When building user context for agents, preferences stored in semantic memories won't be included, and recent episodic memories won't be used (only the old summary field).

**Suggested Fix**:

```python
# After line 35-36, add semantic memory retrieval:
prefs = prof.get("aiPreferences") if isinstance(prof.get("aiPreferences"), dict) else {}
mem = str(prof.get("aiMemorySummary") or "").strip()

# Also query semantic memories for preferences
if user_sub:
    try:
        from ..memory.retrieval.agent_memory_retrieval import get_memories_for_context
        semantic_memories = get_memories_for_context(
            user_sub=user_sub,
            query_text=None,
            memory_types=["SEMANTIC"],
            limit=50,
        )
        # Merge semantic preferences with profile preferences
        for mem_item in semantic_memories:
            metadata = mem_item.get("metadata", {})
            if isinstance(metadata, dict):
                key = metadata.get("key", "")
                value = metadata.get("value")
                if key:
                    prefs[key] = value  # Semantic memories take precedence
    except Exception:
        pass  # Fallback to profile prefs only

# For memory summary, could also include recent episodic memories
# (though aiMemorySummary is a legacy field, so this might be lower priority)
```

**Priority**: Medium-High (affects all agent context building)

---

### 2. `slack_surfaces/home.py` - `_home_view()` (line 36)

**Location**: `backend/app/services/slack_surfaces/home.py`

**Issue**:

- Only checks `prof.get("aiPreferences")` for pinned RFPs and action policy
- Should also check semantic memories for these preferences

**Impact**: Pinned RFPs and action policy stored in semantic memories won't appear in the Slack home view.

**Suggested Fix**:

```python
# After line 36, add semantic memory retrieval:
prefs_raw = prof.get("aiPreferences")
prefs: dict[str, Any] = prefs_raw if isinstance(prefs_raw, dict) else {}

# Also query semantic memories
my_sub = str(prof.get("_id") or prof.get("userSub") or "").strip() or None
if my_sub:
    try:
        from ...memory.retrieval.agent_memory_retrieval import get_memories_for_context
        semantic_memories = get_memories_for_context(
            user_sub=my_sub,
            query_text="preferences pinned actionPolicy",
            memory_types=["SEMANTIC"],
            limit=50,
        )
        # Merge semantic preferences (they take precedence)
        for mem_item in semantic_memories:
            metadata = mem_item.get("metadata", {})
            if isinstance(metadata, dict):
                key = metadata.get("key", "")
                value = metadata.get("value")
                if key in ["pinnedRfpIds", "actionPolicy"] and value:
                    prefs[key] = value
    except Exception:
        pass
```

**Priority**: Medium (affects Slack home view UX)

---

### 3. `slack_action_executor.py` - `update_user_profile` action (lines 213-240, 242-259)

**Location**: `backend/app/services/slack_action_executor.py`

**Issue**:

- When updating preferences via `aiPreferencesMerge`, it only updates the legacy `aiPreferences` field in user profile
- When clearing/appending to memory via `aiMemorySummary`, it only updates the legacy field
- Should also update semantic memories when preferences are changed, or migrate to using semantic memories instead

**Impact**:

- Preferences stored via actions won't be stored in semantic memories (only in legacy field)
- Memory operations won't use the new episodic memory system

**Suggested Fix**:

```python
# After updating aiPreferences (around line 228), also update semantic memories:
if "aiPreferences" in updates:
    try:
        from ..memory.core.agent_memory import update_semantic_memory
        # Store each preference as a semantic memory
        for key, value in merged_prefs.items():
            update_semantic_memory(
                user_sub=user_sub,
                key=key,
                value=value,
                cognito_user_id=user_sub,
                slack_user_id=actor_slack,
                source="slack_action",
            )
    except Exception as e:
        log.warning("semantic_preferences_update_failed", user_sub=user_sub, error=str(e))

# For memory operations, could migrate to episodic memories instead of aiMemorySummary
# (This is a larger change that might need discussion)
```

**Priority**: High (actions that update preferences should store them in the memory system)

---

## Summary

| Location                                            | Issue                            | Priority    | Impact            |
| --------------------------------------------------- | -------------------------------- | ----------- | ----------------- |
| `slack_agent.py` - preferences handler              | ✅ Fixed                         | -           | -                 |
| `agent_context_builder.py` - `build_user_context()` | Only uses legacy fields          | Medium-High | All agent context |
| `slack_surfaces/home.py` - `_home_view()`           | Only uses legacy fields          | Medium      | Slack home view   |
| `slack_action_executor.py` - `update_user_profile`  | Doesn't update semantic memories | High        | Action execution  |

## Recommendations

1. **Immediate**: Fix `slack_action_executor.py` so that when preferences are updated via actions, they're also stored in semantic memories.

2. **Soon**: Update `agent_context_builder.py` to merge semantic memories with profile preferences when building context.

3. **Nice to have**: Update `slack_surfaces/home.py` to also check semantic memories for home view preferences.

## Pattern to Apply

When checking for user preferences or memory, always:

1. Check legacy source (`user_profile.aiPreferences` or `user_profile.aiMemorySummary`)
2. **Also** query semantic/episodic memories using `get_memories_for_context()`
3. Merge results (with semantic memories taking precedence for preferences)
4. Fall back gracefully if memory retrieval fails
