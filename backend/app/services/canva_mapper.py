from __future__ import annotations

import json
import re
from typing import Any


def _get(obj: Any, path: str) -> Any:
    if obj is None or not path:
        return None
    parts = [p for p in str(path).split(".") if p]
    cur: Any = obj
    for p in parts:
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        else:
            return None
    return cur


def _to_text(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, str):
        return val
    if isinstance(val, (int, float, bool)):
        return str(val)
    try:
        return json.dumps(val, indent=2)
    except Exception:
        return str(val)


def guess_source_for_key(key: str) -> str | None:
    k = str(key).lower()
    if "rfp" in k and "title" in k:
        return "rfp.title"
    if "client" in k:
        return "rfp.clientName"
    if "submission" in k or "due" in k:
        return "rfp.submissionDeadline"
    if "proposal" in k and "title" in k:
        return "proposal.title"
    if "cover" in k and "letter" in k:
        return "proposal.sections.Cover Letter.content"
    if k in ("cover_letter", "coverletter"):
        return "proposal.sections.Cover Letter.content"
    if "method" in k or "approach" in k:
        return "proposal.sections.Methodology.content"
    if "deliverable" in k:
        return "proposal.sections.Deliverables.content"
    if "timeline" in k or "schedule" in k:
        return "proposal.sections.Timeline.content"
    if "team" in k or "personnel" in k:
        return "proposal.sections.Team.content"
    if "reference" in k or "past_performance" in k:
        return "proposal.sections.References.content"
    if "executive" in k and "summary" in k:
        return "proposal.sections.Executive Summary.content"
    if "understanding" in k:
        return "proposal.sections.Project Understanding.content"
    return None


def is_likely_auto_filled_key(
    key: str,
    field_type: str,
    *,
    logo_asset_id: str = "",
) -> bool:
    k = str(key).lower()
    if field_type == "image":
        if ("logo" in k or "company_logo" in k) and logo_asset_id:
            return True
        if re.search(
            r"(team|personnel|staff|key_personnel)[^0-9]*([0-9]{1,2}).*(photo|headshot|image)$",
            k,
        ):
            return True

    if field_type == "text":
        if guess_source_for_key(key):
            return True
        if re.search(
            r"(team|personnel|staff|key_personnel)[^0-9]*([0-9]{1,2}).*(name|bio|biography|position|role|title)$",
            k,
        ):
            return True
        if re.search(
            r"(reference|past_performance)[^0-9]*([0-9]{1,2}).*(title|name|client|scope|description|summary|outcome|results)$",
            k,
        ):
            return True

    return False


def build_dataset_values(
    *,
    dataset_def: dict[str, Any],
    mapping: dict[str, Any],
    proposal: dict[str, Any],
    rfp: dict[str, Any],
    company: dict[str, Any] | None,
    company_logo_asset_id: str,
    team_members: list[dict[str, Any]],
    headshot_by_member_id: dict[str, str],
    references: list[dict[str, Any]],
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    logo = str(company_logo_asset_id or "").strip()

    for key, field_def in (dataset_def or {}).items():
        field_type = str((field_def or {}).get("type") or "text")
        if field_type == "chart":
            continue

        m = (mapping or {}).get(key)
        value_obj: dict[str, Any] | None = None

        # Explicit mapping
        if isinstance(m, dict):
            kind = str(m.get("kind") or "")
            if kind == "literal":
                v = _to_text(m.get("value")).strip()
                if field_type == "text" and v:
                    value_obj = {"type": "text", "text": v}
            elif kind == "asset":
                asset_id = str(m.get("assetId") or "").strip()
                if field_type == "image" and asset_id:
                    value_obj = {"type": "image", "asset_id": asset_id}
            elif kind == "source":
                src = str(m.get("source") or "").strip()
                if src:
                    if src.startswith("proposal."):
                        val = _get({"proposal": proposal}, src)
                    elif src.startswith("rfp."):
                        val = _get({"rfp": rfp}, src)
                    elif src.startswith("company."):
                        val = _get({"company": company or {}}, src)
                    else:
                        val = _get({"proposal": proposal, "rfp": rfp, "company": company or {}}, src)
                    v = _to_text(val).strip()
                    if field_type == "text" and v:
                        value_obj = {"type": "text", "text": v}
                    if field_type == "image" and v:
                        value_obj = {"type": "image", "asset_id": v}

        # Heuristic fallback if not mapped
        if not value_obj:
            src = guess_source_for_key(str(key))
            if src:
                if src.startswith("proposal."):
                    val = _get({"proposal": proposal}, src)
                elif src.startswith("rfp."):
                    val = _get({"rfp": rfp}, src)
                elif src.startswith("company."):
                    val = _get({"company": company or {}}, src)
                else:
                    val = _get({"proposal": proposal, "rfp": rfp, "company": company or {}}, src)
                v = _to_text(val).strip()
                if field_type == "text" and v:
                    value_obj = {"type": "text", "text": v}

        # Smart autofill for common key patterns
        if not value_obj:
            k = str(key).lower()

            if field_type == "image" and logo and ("logo" in k or "company_logo" in k):
                value_obj = {"type": "image", "asset_id": logo}

            team_match = re.search(
                r"(team|personnel|staff|key_personnel)[^0-9]*([0-9]{1,2}).*(name|bio|biography|position|role|title|photo|headshot|image)$",
                k,
            )
            if team_match:
                idx = max(0, int(team_match.group(2)) - 1)
                suffix = team_match.group(3)
                member = team_members[idx] if idx < len(team_members) else None
                if member:
                    if field_type == "text":
                        if suffix == "name":
                            value_obj = {"type": "text", "text": _to_text(member.get("nameWithCredentials")).strip()}
                        elif suffix in ("position", "role", "title"):
                            value_obj = {"type": "text", "text": _to_text(member.get("position")).strip()}
                        elif suffix in ("bio", "biography"):
                            value_obj = {"type": "text", "text": _to_text(member.get("biography")).strip()}
                    if field_type == "image" and suffix in ("photo", "headshot", "image"):
                        asset_id = str(headshot_by_member_id.get(str(member.get("memberId")) or "") or "").strip()
                        if asset_id:
                            value_obj = {"type": "image", "asset_id": asset_id}

            ref_match = re.search(
                r"(reference|past_performance)[^0-9]*([0-9]{1,2}).*(title|name|client|scope|description|summary|outcome|results)$",
                k,
            )
            if ref_match and field_type == "text":
                idx = max(0, int(ref_match.group(2)) - 1)
                suffix = ref_match.group(3)
                ref = references[idx] if idx < len(references) else None
                if ref:
                    if suffix in ("title", "name"):
                        value_obj = {"type": "text", "text": _to_text(ref.get("title") or ref.get("projectName") or "").strip()}
                    elif suffix == "client":
                        value_obj = {"type": "text", "text": _to_text(ref.get("clientName") or ref.get("client") or "").strip()}
                    elif suffix in ("scope", "description", "summary"):
                        value_obj = {"type": "text", "text": _to_text(ref.get("description") or ref.get("scope") or ref.get("summary") or "").strip()}
                    elif suffix in ("outcome", "results"):
                        value_obj = {"type": "text", "text": _to_text(ref.get("outcomes") or ref.get("results") or "").strip()}

        if value_obj:
            out[str(key)] = value_obj

    return out


def diagnose_dataset_values(
    *,
    dataset_def: dict[str, Any],
    mapping: dict[str, Any],
    proposal: dict[str, Any],
    rfp: dict[str, Any],
    company: dict[str, Any] | None,
    company_logo_asset_id: str,
    team_members: list[dict[str, Any]],
    headshot_by_member_id: dict[str, str],
    references: list[dict[str, Any]],
) -> dict[str, Any]:
    logo = str(company_logo_asset_id or "").strip()

    values = build_dataset_values(
        dataset_def=dataset_def,
        mapping=mapping,
        proposal=proposal,
        rfp=rfp,
        company=company,
        company_logo_asset_id=company_logo_asset_id,
        team_members=team_members,
        headshot_by_member_id=headshot_by_member_id,
        references=references,
    )

    results: list[dict[str, Any]] = []
    for key, field_def in (dataset_def or {}).items():
        field_type = str((field_def or {}).get("type") or "text")
        m = (mapping or {}).get(key)
        kind = str(m.get("kind") or "") if isinstance(m, dict) else ""

        v = values.get(key)
        filled = v is not None

        source = "blank"
        reason = ""

        if filled:
            source = "mapped" if kind else "auto"
        else:
            if field_type == "chart":
                source = "unsupported"
                reason = "Chart fields are not supported yet."
            elif kind:
                source = "mapped"
                reason = (
                    "Mapping selected but asset_id missing or invalid."
                    if field_type == "image"
                    else "Mapping selected but source/literal produced empty value."
                )
            elif is_likely_auto_filled_key(str(key), field_type, logo_asset_id=logo):
                source = "auto"
                if field_type == "image" and ("logo" in str(key).lower() or "company_logo" in str(key).lower()) and not logo:
                    reason = "Company logo asset_id not found (upload logo)."
                elif field_type == "image":
                    reason = "Auto-fill needs selected team members + uploaded headshots."
                else:
                    reason = "Auto-fill depends on proposal content library selections."
            else:
                reason = "No mapping set for this field."

        preview = ""
        if isinstance(v, dict) and v.get("type") == "text":
            preview = str(v.get("text") or "")[:140]
        elif isinstance(v, dict) and v.get("type") == "image":
            preview = str(v.get("asset_id") or "")

        results.append(
            {
                "key": key,
                "fieldType": field_type,
                "source": source,
                "filled": filled,
                "preview": preview,
                "reason": reason,
                "mapping": {"kind": kind, "source": (m or {}).get("source"), "assetId": (m or {}).get("assetId")}
                if kind
                else None,
            }
        )

    totals = {
        "total": len(results),
        "filled": len([r for r in results if r.get("filled")]),
        "blank": len([r for r in results if not r.get("filled") and r.get("source") != "unsupported"]),
        "unsupported": len([r for r in results if r.get("source") == "unsupported"]),
    }

    return {"totals": totals, "results": results}


