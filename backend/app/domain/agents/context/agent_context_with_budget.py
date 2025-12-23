"""
Helper to add token budget awareness to agent context.
"""

from __future__ import annotations

from typing import Any

from .token_budget_tracker import TokenBudgetTracker


def add_budget_awareness_to_context(
    *,
    context: dict[str, Any],
    token_budget_tracker: TokenBudgetTracker | None,
) -> dict[str, Any]:
    """
    Add token budget status and instructions to agent context.
    
    Args:
        context: Existing context dict
        token_budget_tracker: Token budget tracker (optional)
    
    Returns:
        Updated context with budget awareness
    """
    if not token_budget_tracker:
        return context
    
    # Get budget status message
    budget_status = token_budget_tracker.get_budget_status_message()
    
    # Add budget awareness instructions
    budget_instructions = """
TOKEN_BUDGET_GUIDANCE:
- You have a token budget for this task. Continue working on the problem until the budget is exhausted.
- If you have an answer but budget remains:
  1. Validate and verify your solution thoroughly
  2. Generate additional insights from other context
  3. Explore alternative approaches or edge cases
  4. Acknowledge any uncertainty and explain why you're not fully confident
  5. Think through potential issues or improvements
- When budget is critical (≤10% remaining), prioritize providing your final answer
- If budget becomes exhausted, provide the best answer available based on your work so far
- The budget allows you to think deeply and thoroughly - use it to your advantage

{budget_status}
""".format(budget_status=budget_status).strip()
    
    # Add to context
    if "token_budget_status" not in context:
        context["token_budget_status"] = budget_status
    if "token_budget_instructions" not in context:
        context["token_budget_instructions"] = budget_instructions
    
    return context


def build_budget_aware_system_prompt(
    *,
    base_prompt: str,
    token_budget_tracker: TokenBudgetTracker | None,
) -> str:
    """
    Build a system prompt with budget awareness instructions.
    
    Args:
        base_prompt: Base system prompt
        token_budget_tracker: Token budget tracker (optional)
    
    Returns:
        System prompt with budget awareness added
    """
    if not token_budget_tracker:
        return base_prompt
    
    budget_status = token_budget_tracker.get_budget_status_message()
    budget_instructions = """
TOKEN_BUDGET_GUIDANCE:
- You have a token budget for this task. Continue working on the problem until the budget is exhausted.
- If you have an answer but budget remains:
  1. Validate and verify your solution thoroughly
  2. Generate additional insights from other context  
  3. Explore alternative approaches or edge cases
  4. Acknowledge any uncertainty and explain why you're not fully confident
  5. Think through potential issues or improvements
- When budget is critical (≤10% remaining), prioritize providing your final answer
- If budget becomes exhausted, provide the best answer available based on your work so far

{budget_status}
""".format(budget_status=budget_status).strip()
    
    return f"{base_prompt}\n\n{budget_instructions}"
