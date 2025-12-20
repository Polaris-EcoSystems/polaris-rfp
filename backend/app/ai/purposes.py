from __future__ import annotations

"""
Central inventory of AI purposes used across the app.

Why this exists:
- Purpose strings are used for model routing (Settings.openai_model_for),
  telemetry, and tuning defaults (reasoning/verbosity/token caps).
- Keeping them in one place prevents drift between frontend UX and backend calls.
"""

from dataclasses import dataclass
from typing import Literal


AiPurpose = Literal[
    # RFP analysis
    "rfp_analysis",
    "rfp_analysis_meta",
    "rfp_analysis_dates",
    "rfp_analysis_lists",
    "rfp_section_summary",
    # Proposal generation
    "proposal_sections",
    # Generic writing/editing
    "text_edit",
    "generate_content",
    # Misc AI enrichment
    "buyer_enrichment",
    "section_titles",
    # Slack agent
    "slack_agent",
]


@dataclass(frozen=True)
class PurposeDefaults:
    kind: Literal["json", "text"]
    max_tokens_default: int


PURPOSE_DEFAULTS: dict[str, PurposeDefaults] = {
    # --- RFP analysis ---
    "rfp_analysis": PurposeDefaults(kind="json", max_tokens_default=3000),
    "rfp_analysis_meta": PurposeDefaults(kind="json", max_tokens_default=800),
    "rfp_analysis_dates": PurposeDefaults(kind="json", max_tokens_default=600),
    "rfp_analysis_lists": PurposeDefaults(kind="json", max_tokens_default=1400),
    "rfp_section_summary": PurposeDefaults(kind="text", max_tokens_default=300),
    # --- Proposal generation ---
    "proposal_sections": PurposeDefaults(kind="text", max_tokens_default=1200),
    # --- Generic writing/editing ---
    "text_edit": PurposeDefaults(kind="text", max_tokens_default=4000),
    "generate_content": PurposeDefaults(kind="text", max_tokens_default=4000),
    # --- Misc enrichment ---
    "buyer_enrichment": PurposeDefaults(kind="json", max_tokens_default=900),
    "section_titles": PurposeDefaults(kind="json", max_tokens_default=400),
    # --- Slack ---
    "slack_agent": PurposeDefaults(kind="text", max_tokens_default=1200),
}

