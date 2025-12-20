from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError


Severity = Literal["low", "medium", "high", "critical"]
PricingModel = Literal["fixed_fee", "time_and_materials", "retainer", "milestone", "other"]
InvoicingCadence = Literal["weekly", "biweekly", "monthly", "milestone", "upon_completion", "other"]


class Contact(BaseModel):
    role: str | None = None
    name: str | None = None
    email: str | None = None
    phone: str | None = None


class CommercialTerms(BaseModel):
    pricingModel: PricingModel | None = None
    currency: str | None = Field(default="USD", description="ISO currency code")
    capNte: float | None = Field(default=None, description="Not-to-exceed cap (if applicable)")
    paymentSchedule: str | None = None
    invoicingCadence: InvoicingCadence | None = None
    lateFeePolicy: str | None = None


class Milestone(BaseModel):
    title: str
    dueDate: str | None = None
    acceptanceCriteria: list[str] = Field(default_factory=list)


class Schedule(BaseModel):
    startDate: str | None = None
    endDate: str | None = None
    milestones: list[Milestone] = Field(default_factory=list)


class AssumptionItem(BaseModel):
    text: str
    owner: str | None = None


class RiskMitigationItem(BaseModel):
    risk: str
    severity: Severity = "medium"
    mitigation: str | None = None
    owner: str | None = None


class ChangeControl(BaseModel):
    policyText: str | None = None
    requiresWrittenApproval: bool = True
    allowsVerbalApprovals: bool = False


class InsuranceRequirement(BaseModel):
    kind: str
    required: bool = True
    notes: str | None = None


class ContractingKeyTerms(BaseModel):
    commercialTerms: CommercialTerms = Field(default_factory=CommercialTerms)
    schedule: Schedule = Field(default_factory=Schedule)
    assumptions: list[AssumptionItem] = Field(default_factory=list)
    riskMitigations: list[RiskMitigationItem] = Field(default_factory=list)
    acceptanceCriteria: list[str] = Field(default_factory=list)
    changeControl: ChangeControl = Field(default_factory=ChangeControl)
    insuranceRequirements: list[InsuranceRequirement] = Field(default_factory=list)
    contacts: list[Contact] = Field(default_factory=list)
    additionalTerms: dict[str, Any] = Field(default_factory=dict)


def validate_key_terms(obj: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """
    Validate and normalize key terms, returning (normalized_dict, errors).
    Errors are returned in a frontend-friendly shape.
    """
    try:
        m = ContractingKeyTerms.model_validate(obj or {})
        return (m.model_dump(mode="json"), [])
    except ValidationError as e:
        errs: list[dict[str, Any]] = []
        for it in e.errors(include_url=False):
            errs.append(
                {
                    "loc": [str(x) for x in (it.get("loc") or [])],
                    "msg": str(it.get("msg") or "Invalid value"),
                    "type": str(it.get("type") or ""),
                }
            )
        return ({}, errs)

