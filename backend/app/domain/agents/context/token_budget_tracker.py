"""
Token budget tracker for long-running jobs.

Tracks token usage against a budget, supports checkpointing, and provides
budget awareness to agents.
"""

from __future__ import annotations

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ....observability.logging import get_logger
from .token_counter import calculate_cost, count_tokens, tokens_to_time_budget

log = get_logger("token_budget_tracker")


@dataclass
class TokenUsage:
    """Token usage statistics."""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    model: str | None = None


@dataclass
class TokenBudgetTracker:
    """
    Tracks token budget and usage for a long-running job.
    
    Supports checkpointing and provides budget awareness to agents.
    """
    
    budget_tokens: int
    model: str = "gpt-5.2"
    usage: TokenUsage = field(default_factory=TokenUsage)
    
    def __post_init__(self) -> None:
        """Initialize usage with model."""
        self.usage.model = self.model
    
    def record_llm_call(
        self,
        *,
        input_text: str | list[dict[str, str]] | None = None,
        output_text: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ) -> TokenUsage:
        """
        Record token usage from an LLM call.
        
        Args:
            input_text: Input text/messages (will count tokens if input_tokens not provided)
            output_text: Output text (will count tokens if output_tokens not provided)
            input_tokens: Pre-counted input tokens (optional)
            output_tokens: Pre-counted output tokens (optional)
        
        Returns:
            TokenUsage for this call
        """
        # Count tokens if not provided
        if input_tokens is None:
            input_tokens = count_tokens(input_text or "", model=self.model)
        if output_tokens is None:
            output_tokens = count_tokens(output_text or "", model=self.model)
        
        total = input_tokens + output_tokens
        cost = calculate_cost(input_tokens, output_tokens, model=self.model)
        
        # Update usage
        self.usage.input_tokens += input_tokens
        self.usage.output_tokens += output_tokens
        self.usage.total_tokens += total
        self.usage.cost_usd += cost
        
        call_usage = TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total,
            cost_usd=cost,
            model=self.model,
        )
        
        log.debug(
            "token_usage_recorded",
            call_input_tokens=input_tokens,
            call_output_tokens=output_tokens,
            call_total=total,
            call_cost=cost,
            total_used=self.usage.total_tokens,
            remaining=self.remaining_tokens(),
        )
        
        return call_usage
    
    def remaining_tokens(self) -> int:
        """Get remaining token budget."""
        return max(0, self.budget_tokens - self.usage.total_tokens)
    
    def remaining_budget_percent(self) -> float:
        """Get remaining budget as percentage."""
        if self.budget_tokens == 0:
            return 100.0
        return (self.remaining_tokens() / self.budget_tokens) * 100.0
    
    def is_budget_exhausted(self) -> bool:
        """Check if budget is exhausted."""
        return self.remaining_tokens() <= 0
    
    def can_afford(self, estimated_tokens: int) -> bool:
        """Check if we can afford an estimated token cost."""
        return self.remaining_tokens() >= estimated_tokens
    
    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for text."""
        return count_tokens(text, model=self.model)
    
    def can_add(self, text: str) -> bool:
        """Check if we can add text without exceeding budget."""
        estimated = self.estimate_tokens(text)
        return self.can_afford(estimated)
    
    def remaining(self) -> int:
        """Alias for remaining_tokens() for convenience."""
        return self.remaining_tokens()
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for checkpointing."""
        return {
            "budget_tokens": self.budget_tokens,
            "model": self.model,
            "usage": {
                "input_tokens": self.usage.input_tokens,
                "output_tokens": self.usage.output_tokens,
                "total_tokens": self.usage.total_tokens,
                "cost_usd": self.usage.cost_usd,
            },
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TokenBudgetTracker:
        """Create from dict (for checkpoint restoration)."""
        budget_tokens = int(data.get("budget_tokens", 0))
        model = str(data.get("model", "gpt-5.2"))
        
        tracker = cls(budget_tokens=budget_tokens, model=model)
        
        usage_data = data.get("usage", {})
        tracker.usage.input_tokens = int(usage_data.get("input_tokens", 0))
        tracker.usage.output_tokens = int(usage_data.get("output_tokens", 0))
        tracker.usage.total_tokens = int(usage_data.get("total_tokens", 0))
        tracker.usage.cost_usd = float(usage_data.get("cost_usd", 0.0))
        tracker.usage.model = model
        
        return tracker
    
    @classmethod
    def from_time_budget(
        cls,
        *,
        minutes: float | None = None,
        cost_budget_usd: float | None = None,
        model: str = "gpt-5.2",
        default_minutes: float = 15.0,
    ) -> TokenBudgetTracker:
        """
        Create tracker from time or cost budget.
        
        Uses cost-based conversion: 4 hours = $10 budget, scaled proportionally.
        Default time budget is 15 minutes if not specified.
        
        Args:
            minutes: Time budget in minutes (optional, default: 15)
            cost_budget_usd: Cost budget in USD (optional, overrides time budget)
            model: Model name for calculations
            default_minutes: Default time budget if neither minutes nor cost specified (default: 15)
        
        Returns:
            TokenBudgetTracker instance
        """
        if cost_budget_usd is not None:
            # Cost budget takes precedence
            budget_tokens = tokens_to_time_budget(cost_budget_usd, model=model)
        elif minutes is not None:
            from .token_counter import estimate_time_to_tokens
            budget_tokens = estimate_time_to_tokens(minutes, model=model)
        else:
            # Default: 15 minutes
            from .token_counter import estimate_time_to_tokens
            budget_tokens = estimate_time_to_tokens(default_minutes, model=model)
        
        return cls(budget_tokens=budget_tokens, model=model)
    
    def get_budget_status_message(self) -> str:
        """
        Get a message describing current budget status for agent awareness.
        
        Returns:
            Formatted message for agent context
        """
        remaining = self.remaining_tokens()
        percent = self.remaining_budget_percent()
        used = self.usage.total_tokens
        cost = self.usage.cost_usd
        
        if percent > 50:
            status = "healthy"
        elif percent > 25:
            status = "moderate"
        elif percent > 10:
            status = "low"
        else:
            status = "critical"
        
        message = f"Token Budget Status: {status.upper()}\n"
        message += f"- Budget: {self.budget_tokens:,} tokens\n"
        message += f"- Used: {used:,} tokens ({100.0 - percent:.1f}%)\n"
        message += f"- Remaining: {remaining:,} tokens ({percent:.1f}%)\n"
        message += f"- Cost so far: ${cost:.4f}\n"
        
        if status == "critical":
            message += "\n⚠️ Budget is critically low. Prioritize completing the current task and providing final answer.\n"
        elif status == "low":
            message += "\n⚠️ Budget is low. Consider wrapping up and providing final answer soon.\n"
        elif status == "moderate":
            message += "\n💡 Budget is moderate. Continue working but be mindful of remaining budget.\n"
        else:
            message += "\n✅ Budget is healthy. Continue exploring and refining the solution.\n"
        
        return message
