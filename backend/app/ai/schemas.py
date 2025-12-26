from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class RfpAnalysisAI(BaseModel):
    title: str = ""
    clientName: str = ""
    submissionDeadline: str = "Not available"
    questionsDeadline: str = "Not available"
    bidMeetingDate: str = "Not available"
    bidRegistrationDate: str = "Not available"
    projectDeadline: str = "Not available"
    budgetRange: str = ""
    projectType: str = ""
    location: str = ""
    keyRequirements: list[str] = Field(default_factory=list)
    deliverables: list[str] = Field(default_factory=list)
    criticalInformation: list[str] = Field(default_factory=list)
    timeline: list[str] = Field(default_factory=list)
    contactInformation: str = ""
    clarificationQuestions: list[str] = Field(default_factory=list)


# --- RFP analysis (split) ---
# These are intentionally small so we can call the model for each "bucket" and
# merge results server-side (fewer schema failures; easy to parallelize).
class RfpMetaAI(BaseModel):
    title: str = ""
    clientName: str = ""
    budgetRange: str = ""
    projectType: str = ""
    location: str = ""
    contactInformation: str = ""


class RfpDatesAI(BaseModel):
    submissionDeadline: str = "Not available"
    questionsDeadline: str = "Not available"
    bidMeetingDate: str = "Not available"
    bidRegistrationDate: str = "Not available"
    projectDeadline: str = "Not available"


class RfpListsAI(BaseModel):
    keyRequirements: list[str] = Field(default_factory=list)
    deliverables: list[str] = Field(default_factory=list)
    criticalInformation: list[str] = Field(default_factory=list)
    timeline: list[str] = Field(default_factory=list)
    clarificationQuestions: list[str] = Field(default_factory=list)


class SectionTitlesAI(BaseModel):
    titles: list[str] = Field(default_factory=list)


class BuyerEnrichmentAI(BaseModel):
    personaSummary: str = ""
    likelyGoals: list[str] = Field(default_factory=list)
    likelyConcerns: list[str] = Field(default_factory=list)
    bestAngles: list[str] = Field(default_factory=list)


class EvidenceItem(BaseModel):
    type: Literal["project", "reference"]
    id: str
    label: str


class CapabilitiesStatementAI(BaseModel):
    statementMarkdown: str = ""
    capabilities: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    projectIds: list[str] = Field(default_factory=list)
    referenceIds: list[str] = Field(default_factory=list)
    evidenceItems: list[EvidenceItem] = Field(default_factory=list)


class AiEditTextRequest(BaseModel):
    text: str | None = None
    selectedText: str | None = None
    prompt: str


class AiEditTextResponse(BaseModel):
    success: bool = True
    editedText: str
    originalText: str
    prompt: str


class AiGenerateContentRequest(BaseModel):
    prompt: str
    context: str | None = None
    contentType: str | None = None


class AiGenerateContentResponse(BaseModel):
    success: bool = True
    content: str
    prompt: str
    contentType: str

