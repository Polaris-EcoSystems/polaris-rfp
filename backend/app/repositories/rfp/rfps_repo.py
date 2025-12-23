from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from boto3.dynamodb.conditions import Key

from ...db.dynamodb.table import get_main_table
from ...domain.rfp.rfp_logic import check_disqualification, compute_date_sanity, compute_fit_score


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def type_pk(t: str) -> str:
    return f"TYPE#{t}"


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4()}"


def rfp_key(rfp_id: str) -> dict[str, str]:
    return {"pk": f"RFP#{rfp_id}", "sk": "PROFILE"}


def _rfp_type_item(rfp_id: str, created_at: str) -> dict[str, str]:
    return {"gsi1pk": type_pk("RFP"), "gsi1sk": f"{created_at}#{rfp_id}"}


def normalize_rfp_for_api(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if not item:
        return None

    obj = dict(item)
    obj["_id"] = item.get("rfpId")

    for k in ("pk", "sk", "gsi1pk", "gsi1sk", "entityType", "rfpId"):
        obj.pop(k, None)

    disq = check_disqualification(obj)
    obj["isDisqualified"] = bool(disq)

    ds = compute_date_sanity(obj)
    obj["dateWarnings"] = ds.get("warnings")
    obj["dateMeta"] = ds.get("meta")

    fit = compute_fit_score(obj)
    obj["fitScore"] = fit.get("score")
    obj["fitReasons"] = fit.get("reasons")

    return obj


def create_rfp_from_analysis(
    *, 
    analysis: dict[str, Any], 
    source_file_name: str, 
    source_file_size: int,
    source_pdf_data: bytes | None = None,
    source_s3_key: str | None = None,
) -> dict[str, Any]:
    rfp_id = new_id("rfp")
    item = build_rfp_item_from_analysis(
        rfp_id=rfp_id,
        analysis=analysis,
        source_file_name=source_file_name,
        source_file_size=source_file_size,
    )
    get_main_table().put_item(item=item, condition_expression="attribute_not_exists(pk)")
    result = normalize_rfp_for_api(item) or {}
    
    # Trigger folder creation, template population, and PDF upload (background, best-effort)
    try:
        from ...infrastructure.integrations.drive.drive_project_setup import setup_project_folders
        from ...infrastructure.integrations.drive.drive_template_populator import populate_project_templates
        from ...repositories.rfp.opportunity_state_repo import ensure_state_exists, patch_state
        
        # Create folders
        folder_result = setup_project_folders(rfp_id=rfp_id)
        if folder_result.get("ok"):
            folders = folder_result.get("folders", {})
            
            # Store folder IDs in OpportunityState
            try:
                ensure_state_exists(rfp_id=rfp_id)
                patch_state(
                    rfp_id=rfp_id,
                    patch={"driveFolders": folders},
                    create_snapshot=False,
                )
            except Exception as e:
                from ...observability.logging import get_logger
                log = get_logger("rfps_repo")
                log.warning("failed_to_store_drive_folders", rfp_id=rfp_id, error=str(e))
            
            # Populate templates
            try:
                templates_folder = folders.get("templates")
                financial_folder = folders.get("financial")
                populate_project_templates(
                    rfp_id=rfp_id,
                    templates_folder_id=templates_folder,
                    financial_folder_id=financial_folder,
                )
            except Exception as e:
                from ...observability.logging import get_logger
                log = get_logger("rfps_repo")
                log.warning("template_population_failed", rfp_id=rfp_id, error=str(e))
            
            # Upload PDF to Drive "RFP Files" folder
            try:
                rfp_files_folder_id = folders.get("rfpfiles") or folders.get("root")
                if rfp_files_folder_id:
                    pdf_data = source_pdf_data
                    
                    # If we don't have PDF data but have S3 key, download it
                    if not pdf_data and source_s3_key:
                        from ...infrastructure.storage.s3_assets import get_object_bytes
                        try:
                            pdf_data = get_object_bytes(key=source_s3_key, max_bytes=60 * 1024 * 1024)
                        except Exception:
                            pdf_data = None
                    
                    if pdf_data:
                        from ...tools.categories.google.google_drive import upload_file_to_drive
                        from datetime import datetime, timezone
                        
                        # Use sanitized filename
                        pdf_filename = source_file_name or "rfp.pdf"
                        if not pdf_filename.lower().endswith(".pdf"):
                            pdf_filename = f"{pdf_filename}.pdf"
                        
                        upload_result = upload_file_to_drive(
                            name=pdf_filename,
                            content=pdf_data,
                            mime_type="application/pdf",
                            folder_id=rfp_files_folder_id,
                        )
                        
                        if upload_result.get("ok"):
                            file_id = upload_result.get("fileId")
                            # Store file reference in OpportunityState
                            try:
                                patch_state(
                                    rfp_id=rfp_id,
                                    patch={
                                        "driveFiles_append": [{
                                            "fileId": file_id,
                                            "fileName": pdf_filename,
                                            "folderId": rfp_files_folder_id,
                                            "category": "source_pdf",
                                            "uploadedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                                        }]
                                    },
                                    create_snapshot=False,
                                )
                            except Exception:
                                pass  # Non-fatal
            except Exception as e:
                from ...observability.logging import get_logger
                log = get_logger("rfps_repo")
                log.warning("pdf_upload_to_drive_failed", rfp_id=rfp_id, error=str(e))
    except Exception as e:
        # Non-fatal - log but don't fail RFP creation
        from ...observability.logging import get_logger
        log = get_logger("rfps_repo")
        log.warning("auto_folder_setup_failed", rfp_id=rfp_id, error=str(e))
    
    return result


def build_rfp_item_from_analysis(
    *,
    rfp_id: str,
    analysis: dict[str, Any],
    source_file_name: str,
    source_file_size: int,
) -> dict[str, Any]:
    """
    Build the DynamoDB item for an RFP record.

    This is used by both the normal create path and the de-dupe transactional path.
    """
    rid = str(rfp_id or "").strip()
    if not rid:
        raise ValueError("rfp_id is required")
    created_at = now_iso()

    item: dict[str, Any] = {
        **rfp_key(rid),
        "entityType": "RFP",
        "rfpId": rid,
        "createdAt": created_at,
        "updatedAt": created_at,
        **(analysis or {}),
        "fileName": source_file_name or "",
        "fileSize": int(source_file_size or 0),
        "clientName": (analysis or {}).get("clientName") or "Unknown Client",
        **_rfp_type_item(rid, created_at),
    }
    return item


def get_rfp_by_id(rfp_id: str) -> dict[str, Any] | None:
    item = get_main_table().get_item(key=rfp_key(rfp_id))
    return normalize_rfp_for_api(item)


def list_rfps(page: int = 1, limit: int = 20, next_token: str | None = None) -> dict[str, Any]:
    """List RFPs via cursor pagination.

    - Primary pagination mechanism is `next_token` (opaque encrypted cursor).
    - `page` is kept for backward compatibility but is implemented by advancing
      the cursor `page-1` times, which can be expensive.
    """
    p = max(1, int(page or 1))
    lim = max(1, min(200, int(limit or 20)))

    t = get_main_table()
    token = next_token

    # Back-compat: if a caller requests a deeper \"page\" without providing a token,
    # advance the cursor `page-1` times.
    if not token and p > 1:
        for _ in range(1, p):
            pg = t.query_page(
                index_name="GSI1",
                key_condition_expression=Key("gsi1pk").eq(type_pk("RFP")),
                scan_index_forward=False,
                limit=lim,
                next_token=token,
            )
            token = pg.next_token
            if not token:
                break

    page_resp = t.query_page(
        index_name="GSI1",
        key_condition_expression=Key("gsi1pk").eq(type_pk("RFP")),
        scan_index_forward=False,
        limit=lim,
        next_token=token,
    )

    data: list[dict[str, Any]] = []
    for it in page_resp.items:
        norm = normalize_rfp_for_api(it)
        if norm:
            data.append(norm)

    return {
        "data": data,
        "nextToken": page_resp.next_token,
        # Keep a small pagination object for legacy callers. Totals are not computed
        # in cursor mode (would require extra scans/queries).
        "pagination": {"page": p, "limit": lim},
    }


def update_rfp(rfp_id: str, updates_obj: dict[str, Any]) -> dict[str, Any] | None:
    allowed = {
        "title",
        "clientName",
        "submissionDeadline",
        "questionsDeadline",
        "bidMeetingDate",
        "bidRegistrationDate",
        "budgetRange",
        "keyRequirements",
        "deliverables",
        "criticalInformation",
        "timeline",
        "projectDeadline",
        "projectType",
        "contactInformation",
        "location",
        "clarificationQuestions",
        "sectionTitles",
        "buyerProfiles",
        # Source artifact (original PDF) for viewing/downloading
        "sourceS3Key",
        "sourceS3Uri",
        # AI artifacts (only written by server-side flows)
        "rawText",
        "_analysis",
        "aiSummary",
        "aiSummaryUpdatedAt",
        # Review workflow (bid/no-bid decision, notes, etc.)
        "review",
    }

    updates = {k: v for k, v in (updates_obj or {}).items() if k in allowed}

    now = now_iso()
    expr_parts: list[str] = []
    expr_names: dict[str, str] = {}
    expr_values: dict[str, Any] = {":u": now}

    i = 0
    for k, v in updates.items():
        i += 1
        nk = f"#k{i}"
        vk = f":v{i}"
        expr_names[nk] = k
        expr_values[vk] = v
        expr_parts.append(f"{nk} = {vk}")

    expr_parts.append("updatedAt = :u")

    updated = get_main_table().update_item(
        key=rfp_key(rfp_id),
        update_expression="SET " + ", ".join(expr_parts),
        expression_attribute_names=expr_names if expr_names else None,
        expression_attribute_values=expr_values,
        return_values="ALL_NEW",
    )

    return normalize_rfp_for_api(updated)


def delete_rfp(rfp_id: str) -> None:
    get_main_table().delete_item(key=rfp_key(rfp_id))


def list_rfp_proposal_summaries(rfp_id: str) -> list[dict[str, Any]]:
    t = get_main_table()
    items: list[dict[str, Any]] = []
    tok: str | None = None
    while True:
        pg = t.query_page(
            key_condition_expression=Key("pk").eq(f"RFP#{rfp_id}")
            & Key("sk").begins_with("PROPOSAL#"),
            scan_index_forward=False,
            limit=200,
            next_token=tok,
        )
        items.extend(pg.items)
        tok = pg.next_token
        if not tok or not pg.items:
            break

    out: list[dict[str, Any]] = []
    for it in items:
        o = dict(it)
        o.pop("pk", None)
        o.pop("sk", None)
        out.append(o)
    return out
