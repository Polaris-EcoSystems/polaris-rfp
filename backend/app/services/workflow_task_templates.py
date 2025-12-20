from __future__ import annotations

from typing import TypedDict


PipelineStage = str


class StageTaskTemplate(TypedDict):
    templateId: str
    title: str
    description: str


STAGE_TASK_TEMPLATES: dict[PipelineStage, list[StageTaskTemplate]] = {
    "BidDecision": [
        {
            "templateId": "bid_confirm_deadline_sanity",
            "title": "Confirm deadline sanity",
            "description": "Verify submission deadline and internal timeline are realistic.",
        },
        {
            "templateId": "bid_review_suitability",
            "title": "Review suitability",
            "description": "Assess fit, risks, and any disqualifiers.",
        },
        {
            "templateId": "bid_make_decision",
            "title": "Make bid decision",
            "description": "Decide bid / no-bid and capture rationale.",
        },
        {
            "templateId": "bid_assign_proposal_lead",
            "title": "Assign proposal lead",
            "description": "Assign the owner responsible for drafting and shepherding the proposal.",
        },
    ],
    "ProposalDraft": [
        {
            "templateId": "draft_create_proposal",
            "title": "Create proposal draft",
            "description": "Generate or create the proposal and confirm the template/sections.",
        },
        {
            "templateId": "draft_assign_sections",
            "title": "Assign sections / contributors",
            "description": "Assign owners for key sections and supporting inputs.",
        },
        {
            "templateId": "draft_first_pass",
            "title": "Draft first pass",
            "description": "Complete a first pass of all sections with placeholders removed.",
        },
    ],
    "ReviewRebuttal": [
        {
            "templateId": "review_internal_review",
            "title": "Internal review",
            "description": "Review draft for completeness, compliance, and quality.",
        },
        {
            "templateId": "review_capture_rework",
            "title": "Capture rework list",
            "description": "Document changes needed and move proposal status if required.",
        },
    ],
    "Rework": [
        {
            "templateId": "rework_apply_changes",
            "title": "Apply requested changes",
            "description": "Address review feedback and update the proposal sections.",
        },
        {
            "templateId": "rework_ready_for_review",
            "title": "Mark ready for review",
            "description": "Move proposal back to review when rework is complete.",
        },
    ],
    "ReadyToSubmit": [
        {
            "templateId": "submit_final_checks",
            "title": "Final compliance checks",
            "description": "Confirm formatting, required forms, and submission instructions.",
        },
        {
            "templateId": "submit_send",
            "title": "Submit proposal",
            "description": "Submit to the client and record submission confirmation.",
        },
    ],
    "Contracting": [
        {
            "templateId": "contracting_create_case",
            "title": "Start contracting",
            "description": "Confirm win, assign an owner, and capture initial contracting notes.",
        },
        {
            "templateId": "contracting_generate_contract",
            "title": "Generate contract draft",
            "description": "Generate the initial contract draft from approved templates and proposal data.",
        },
        {
            "templateId": "contracting_legal_review",
            "title": "Legal review / risk mitigations",
            "description": "Review legal language, assumptions, and risk mitigations; document changes.",
        },
        {
            "templateId": "contracting_finalize_budget",
            "title": "Finalize project budget (internal)",
            "description": "Finalize budget model and generate the internal Excel workbook.",
        },
        {
            "templateId": "contracting_collect_supporting_docs",
            "title": "Collect required supporting documents",
            "description": "Upload insurance certificates, certifications, and any required client forms.",
        },
        {
            "templateId": "contracting_publish_package",
            "title": "Publish client package",
            "description": "Assemble contract + budget + supporting docs into a client portal package and publish a link.",
        },
        {
            "templateId": "contracting_esign_send",
            "title": "Send for signature",
            "description": "Send the contract for signature (provider stub for now) and track status.",
        },
        {
            "templateId": "contracting_archive",
            "title": "Archive contracting artifacts",
            "description": "Record countersignature, store final versions, and archive the package.",
        },
    ],
    "Submitted": [],
    "NoBid": [],
    "Disqualified": [],
}

