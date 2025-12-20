"""
Agent tool registries and implementations.

Design goals:
- Read vs write separation (writes must be approval-gated elsewhere).
- Bounded outputs (avoid flooding model context).
- Minimal dependencies on Slack-specific code so tools can be reused by API endpoints.
"""

