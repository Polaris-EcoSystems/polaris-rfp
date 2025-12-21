"""
Slack formatting guide for AI agents.
This module provides formatting instructions for Slack mrkdwn syntax.
"""

SLACK_FORMATTING_GUIDE = """
CRITICAL: You are responding in Slack, which uses Slack mrkdwn formatting (NOT standard Markdown).

Slack mrkdwn Formatting Rules:
- Bold: Use *bold* (single asterisks, NOT double asterisks)
- Italic: Use _italic_ (underscores, NOT single asterisks)
- Strikethrough: Use ~strike~
- Code (inline): Use `code` (backticks)
- Code blocks: Use triple backticks ```code block```
- Line breaks: Use \n (not just line breaks)
- Block quotes: Start lines with > character
- Lists: Use - item (just dashes with newlines, no special syntax)
- Links: Use <url|text> format, e.g., <https://example.com|Click here>
- User mentions: Use <@U123456> format (user ID, not @username)
- Channel mentions: Use <#C123456> format (channel ID, not #channel-name)
- Special characters: Escape & as &amp;, < as &lt;, > as &gt; if not using for formatting

Examples:
- Bold text: *This is bold* (NOT **This is bold**)
- Italic text: _This is italic_ (NOT *This is italic*)
- Link: <https://example.com|Example Site>
- Code: `variable_name`
- List:
  - Item 1
  - Item 2
- Block quote:
  > This is quoted text

Common mistakes to avoid:
- Do NOT use **double asterisks** for bold (use *single asterisks*)
- Do NOT use *single asterisks* for italic (use _underscores_)
- Do NOT use @username for mentions (use <@U123456> format with user ID)
- Do NOT use #channel-name for channels (use <#C123456> format with channel ID)
- Do NOT use [text](url) link format (use <url|text> format)

Your responses will be displayed in Slack, so always use Slack mrkdwn formatting, not standard Markdown.
"""
