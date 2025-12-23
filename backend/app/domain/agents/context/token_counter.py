"""
Token counting and cost calculation service.

Uses tiktoken to count tokens and calculate costs based on OpenAI pricing.
Supports model detection and fallback tokenizers.
"""

from __future__ import annotations

import tiktoken

from ...observability.logging import get_logger

log = get_logger("token_counter")

# OpenAI pricing per 1M tokens (as of implementation date)
# Source: https://openai.com/api/pricing/
PRICING: dict[str, dict[str, float]] = {
    "gpt-5.2": {
        "input": 1.75,  # $1.75 per 1M tokens
        "output": 14.00,  # $14.00 per 1M tokens
    },
    "gpt-4o": {
        "input": 2.50,
        "output": 10.00,
    },
    "gpt-4o-mini": {
        "input": 0.150,
        "output": 0.600,
    },
    "gpt-4-turbo": {
        "input": 10.00,
        "output": 30.00,
    },
    "gpt-4": {
        "input": 30.00,
        "output": 60.00,
    },
    "gpt-3.5-turbo": {
        "input": 0.50,
        "output": 1.50,
    },
}

# Tokenizer mapping (model -> tiktoken encoding name)
# For models without direct tiktoken support, use closest equivalent
TOKENIZER_MAP: dict[str, str] = {
    "gpt-5.2": "o200k_base",  # GPT-5 uses o200k_base tokenizer
    "gpt-4o": "o200k_base",
    "gpt-4o-mini": "o200k_base",
    "gpt-4-turbo": "cl100k_base",
    "gpt-4": "cl100k_base",
    "gpt-3.5-turbo": "cl100k_base",
}

# Context window sizes (approximate, in tokens)
CONTEXT_WINDOWS: dict[str, int] = {
    "gpt-5.2": 400000,  # 400k context window
    "gpt-4o": 128000,
    "gpt-4o-mini": 128000,
    "gpt-4-turbo": 128000,
    "gpt-4": 8192,
    "gpt-3.5-turbo": 16385,
}

# Default encoding fallback
DEFAULT_ENCODING = "cl100k_base"  # GPT-4/GPT-3.5 encoding


def detect_tokenizer(model: str | None) -> str:
    """
    Detect the appropriate tiktoken encoding for a model.
    
    Args:
        model: Model name (e.g., "gpt-5.2", "gpt-4o")
    
    Returns:
        Tiktoken encoding name
    """
    if not model:
        return DEFAULT_ENCODING
    
    model_lower = str(model).lower().strip()
    
    # Direct mapping
    if model_lower in TOKENIZER_MAP:
        return TOKENIZER_MAP[model_lower]
    
    # Fallback logic
    if "gpt-5" in model_lower or "o200k" in model_lower:
        return "o200k_base"
    elif "gpt-4" in model_lower:
        return "cl100k_base"
    elif "gpt-3.5" in model_lower:
        return "cl100k_base"
    else:
        # Default fallback
        log.warning("tokenizer_fallback", model=model, encoding=DEFAULT_ENCODING)
        return DEFAULT_ENCODING


def get_encoding(model: str | None) -> tiktoken.Encoding:
    """
    Get tiktoken encoding for a model.
    
    Args:
        model: Model name
    
    Returns:
        Tiktoken Encoding object
    """
    encoding_name = detect_tokenizer(model)
    try:
        return tiktoken.get_encoding(encoding_name)
    except Exception as e:
        log.warning("tokenizer_get_failed", encoding=encoding_name, error=str(e))
        # Fallback to default
        try:
            return tiktoken.get_encoding(DEFAULT_ENCODING)
        except Exception:
            # Last resort: try cl100k_base
            return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str | list[dict[str, str]] | list[str], model: str | None = None) -> int:
    """
    Count tokens in text or messages.
    
    Args:
        text: Text string, list of message dicts, or list of strings
        model: Model name for tokenizer selection (optional)
    
    Returns:
        Number of tokens
    """
    if not text:
        return 0
    
    enc = get_encoding(model)
    
    try:
        if isinstance(text, str):
            return len(enc.encode(text))
        elif isinstance(text, list):
            # Handle list of message dicts (OpenAI format)
            if text and isinstance(text[0], dict):
                # Format: [{"role": "user", "content": "..."}, ...]
                total = 0
                for msg in text:
                    if isinstance(msg, dict):
                        content = msg.get("content")
                        if content:
                            if isinstance(content, str):
                                total += len(enc.encode(content))
                            elif isinstance(content, list):
                                # Handle content arrays (e.g., with images)
                                for item in content:
                                    if isinstance(item, dict) and item.get("type") == "text":
                                        total += len(enc.encode(str(item.get("text", ""))))
                        # Add tokens for role formatting (approx 4 tokens per message)
                        total += 4
                return total
            else:
                # List of strings
                total = 0
                for s in text:
                    if s:
                        total += len(enc.encode(str(s)))
                return total
        else:
            # Convert to string as fallback
            return len(enc.encode(str(text)))
    except Exception as e:
        log.warning("token_count_failed", error=str(e), text_type=type(text).__name__)
        # Rough estimate: ~4 characters per token
        text_str = str(text)
        return len(text_str) // 4


def calculate_cost(input_tokens: int, output_tokens: int, model: str | None = None) -> float:
    """
    Calculate cost in USD for token usage.
    
    Args:
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        model: Model name for pricing lookup
    
    Returns:
        Cost in USD
    """
    if not model:
        model = "gpt-4o"  # Default
    
    model_lower = str(model).lower().strip()
    
    # Find pricing (try exact match, then partial match)
    pricing = None
    if model_lower in PRICING:
        pricing = PRICING[model_lower]
    else:
        # Try to find closest match
        for model_key in PRICING:
            if model_key in model_lower or model_lower in model_key:
                pricing = PRICING[model_key]
                break
    
    if not pricing:
        # Fallback to gpt-4o pricing
        pricing = PRICING.get("gpt-4o", {"input": 2.50, "output": 10.00})
        log.warning("pricing_fallback", model=model, using="gpt-4o")
    
    input_cost = (input_tokens / 1_000_000) * pricing.get("input", 0)
    output_cost = (output_tokens / 1_000_000) * pricing.get("output", 0)
    
    return input_cost + output_cost


def estimate_time_to_tokens(minutes: float, model: str | None = None, tokens_per_minute: int | None = None) -> int:
    """
    Estimate token budget from time budget.
    
    Uses cost-based conversion: 4 hours = $10 budget, scaled proportionally.
    This ensures consistent token allocation regardless of time duration.
    
    Args:
        minutes: Time budget in minutes
        model: Model name (for pricing)
        tokens_per_minute: Optional override (default: uses cost-based conversion)
    
    Returns:
        Estimated token budget
    """
    if tokens_per_minute is not None:
        # Legacy heuristic mode if explicitly provided
        estimated = int(minutes * tokens_per_minute)
        log.debug("time_to_tokens_estimate_heuristic", minutes=minutes, tokens=estimated, model=model)
        return estimated
    
    # Cost-based conversion: 4 hours = $10 budget
    # Scale proportionally: cost = (minutes / 240) * $10
    HOURS_TO_COST_BUDGET = 4.0  # 4 hours
    COST_BUDGET_FOR_HOURS = 10.0  # $10
    
    hours = minutes / 60.0
    cost_budget = (hours / HOURS_TO_COST_BUDGET) * COST_BUDGET_FOR_HOURS
    
    # Convert cost to tokens (conservative, using output pricing)
    estimated = tokens_to_time_budget(cost_budget, model=model)
    
    log.debug("time_to_tokens_estimate_cost_based", minutes=minutes, hours=hours, cost_usd=cost_budget, tokens=estimated, model=model)
    
    return estimated


def tokens_to_time_budget(cost_budget_usd: float, model: str | None = None) -> int:
    """
    Convert cost budget to maximum token budget.
    
    Uses worst-case pricing (output tokens, which are more expensive) to ensure
    we stay within budget even if all tokens are outputs.
    
    Args:
        cost_budget_usd: Maximum cost in USD (e.g., 10.0 for $10)
        model: Model name for pricing lookup
    
    Returns:
        Maximum token budget (conservative estimate)
    """
    if not model:
        model = "gpt-5.2"  # Default to most expensive for safety
    
    model_lower = str(model).lower().strip()
    
    # Get pricing
    pricing = PRICING.get(model_lower, PRICING.get("gpt-5.2", {"input": 1.75, "output": 14.00}))
    
    # Use output pricing (most expensive) for conservative estimate
    output_price_per_1m = pricing.get("output", 14.00)
    
    # Calculate max tokens assuming all are outputs
    max_tokens = int((cost_budget_usd / output_price_per_1m) * 1_000_000)
    
    log.debug("cost_to_tokens", cost_usd=cost_budget_usd, max_tokens=max_tokens, model=model)
    
    return max_tokens


def get_context_window(model: str | None = None) -> int:
    """
    Get context window size for a model.
    
    Args:
        model: Model name
    
    Returns:
        Context window size in tokens
    """
    if not model:
        return 400000  # Default to 400k
    
    model_lower = str(model).lower().strip()
    return CONTEXT_WINDOWS.get(model_lower, 400000)
