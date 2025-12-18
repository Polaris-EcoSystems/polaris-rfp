from __future__ import annotations

from fastapi import APIRouter, HTTPException
from openai import OpenAI

from ..settings import settings

router = APIRouter(tags=["ai"])


def _client() -> OpenAI:
    if not settings.openai_api_key:
        raise HTTPException(status_code=500, detail="OpenAI API key not configured")
    return OpenAI(api_key=settings.openai_api_key)


@router.post("/edit-text")
def edit_text(body: dict):
    text = (body or {}).get("text")
    selected_text = (body or {}).get("selectedText")
    prompt = str((body or {}).get("prompt") or "").strip()

    if not text and not selected_text:
        raise HTTPException(
            status_code=400, detail="Either text or selectedText must be provided"
        )
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt is required")

    text_to_process = str(selected_text or text or "")

    system_prompt = (
        "You are an expert proposal writer and editor. Your PRIMARY GOAL is to "
        "FOLLOW THE USER'S INSTRUCTION EXACTLY and make changes that directly "
        "address their specific request.\n\n"
        "CRITICAL INSTRUCTIONS:\n"
        "- READ THE USER'S PROMPT CAREFULLY and understand what they want\n"
        "- FOCUS ENTIRELY on applying the user's specific instruction\n"
        "- If they ask to \"make professional\" - enhance professionalism\n"
        "- If they ask to \"add details\" - expand with specific information\n"
        "- If they ask to \"make technical\" - add technical terminology and depth\n"
        "- If they ask to \"shorten\" - condense while keeping key points\n"
        "- If they ask to \"improve\" - make substantial quality enhancements\n"
        "- ALWAYS make VISIBLE, SIGNIFICANT changes that match the user's intent\n"
        "- Preserve markdown formatting (**, *, bullet points, tables with |, etc.)\n"
        "- Return ONLY the edited text with NO explanations or meta-commentary\n\n"
        "IMPORTANT: The user's instruction is the HIGHEST PRIORITY. Whatever they "
        "ask for, deliver it with clear, substantial changes. Don't be subtle - make "
        "bold transformations that match their request."
    )

    user_prompt = (
        f'USER\'S SPECIFIC INSTRUCTION: "{prompt}"\n\n'
        f"Original text:\n{text_to_process}\n\n"
        "Apply the above instruction and make clear, substantial changes that "
        "directly address what the user asked for. Be bold and make the changes obvious."
    )

    try:
        completion = _client().chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=4000,
            temperature=0.7,
        )
        edited_text = (completion.choices[0].message.content or "").strip()
        return {
            "success": True,
            "editedText": edited_text,
            "originalText": text_to_process,
            "prompt": prompt,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"error": "Failed to process text with AI", "details": str(e)},
        )


@router.post("/generate-content")
def generate_content(body: dict):
    prompt = str((body or {}).get("prompt") or "").strip()
    context = (body or {}).get("context")
    content_type = str((body or {}).get("contentType") or "general")

    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt is required")

    system_prompt = (
        "You are an expert proposal writer and business content specialist. Your "
        "PRIMARY GOAL is to generate content that EXACTLY matches what the user is asking for.\n\n"
        "CRITICAL GUIDELINES:\n"
        "- UNDERSTAND THE USER'S REQUEST thoroughly before generating content\n"
        "- DELIVER EXACTLY what they asked for - no more, no less (unless they ask for comprehensive content)\n"
        "- If they ask for \"a paragraph\" - provide a well-written paragraph\n"
        "- If they ask for \"bullet points\" - provide formatted bullet points\n"
        "- If they ask for \"detailed explanation\" - provide 300-600 words with specific details\n"
        "- If they ask for \"brief overview\" - provide concise, focused content (100-200 words)\n"
        "- Use professional, appropriate language for business/technical documents\n"
        "- Include SPECIFIC details, examples, and concrete information when relevant\n"
        "- Use markdown formatting effectively (**, *, bullet points, numbered lists, tables)\n"
        "- Match the tone and style to the content type and user's request\n"
        "- Be thorough when asked, concise when requested\n\n"
        f"Content Type: {content_type}\n\n"
        "IMPORTANT: The user's request is your top priority. Deliver exactly what "
        "they're asking for with high quality and relevant detail."
    )

    if context:
        system_prompt += f"\n\nADDITIONAL CONTEXT TO INCORPORATE:\n{context}"

    user_prompt = (
        f"USER'S REQUEST: {prompt}\n\n"
        "Generate content that directly addresses the above request. Match the scope, "
        "detail level, and format to what the user is asking for."
    )

    try:
        completion = _client().chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=4000,
            temperature=0.6,
        )
        generated = (completion.choices[0].message.content or "").strip()
        return {
            "success": True,
            "content": generated,
            "prompt": prompt,
            "contentType": content_type,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"error": "Failed to generate content with AI", "details": str(e)},
        )
