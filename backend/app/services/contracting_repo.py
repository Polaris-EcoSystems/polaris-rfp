from __future__ import annotations

import base64
import hashlib
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from boto3.dynamodb.conditions import Key

from ..db.dynamodb.errors import DdbNotFound
from ..db.dynamodb.table import get_main_table
from ..settings import settings


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _type_pk(t: str) -> str:
    return f"TYPE#{t}"


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4()}"


# -----------------------------
# Keys / entity helpers
# -----------------------------


def contracting_case_key(case_id: str) -> dict[str, str]:
    cid = str(case_id or "").strip()
    if not cid:
        raise ValueError("case_id is required")
    return {"pk": f"CONTRACTING#{cid}", "sk": "PROFILE"}


def contracting_case_gsi_pk(proposal_id: str) -> str:
    pid = str(proposal_id or "").strip()
    if not pid:
        raise ValueError("proposal_id is required")
    return f"PROPOSAL_CONTRACTING#{pid}"


def contract_template_key(template_id: str) -> dict[str, str]:
    tid = str(template_id or "").strip()
    if not tid:
        raise ValueError("template_id is required")
    return {"pk": f"CONTRACT_TEMPLATE#{tid}", "sk": "PROFILE"}


def contract_template_version_key(template_id: str, version_id: str) -> dict[str, str]:
    tid = str(template_id or "").strip()
    vid = str(version_id or "").strip()
    if not tid:
        raise ValueError("template_id is required")
    if not vid:
        raise ValueError("version_id is required")
    return {"pk": f"CONTRACT_TEMPLATE#{tid}", "sk": f"VERSION#{vid}"}


def _contracting_child_key(case_id: str, sk: str) -> dict[str, str]:
    cid = str(case_id or "").strip()
    if not cid:
        raise ValueError("case_id is required")
    skv = str(sk or "").strip()
    if not skv:
        raise ValueError("sk is required")
    return {"pk": f"CONTRACTING#{cid}", "sk": skv}


def contract_doc_version_key(case_id: str, version_id: str) -> dict[str, str]:
    vid = str(version_id or "").strip()
    if not vid:
        raise ValueError("version_id is required")
    return _contracting_child_key(case_id, f"CONTRACT_DOC#{vid}")


def budget_version_key(case_id: str, version_id: str) -> dict[str, str]:
    vid = str(version_id or "").strip()
    if not vid:
        raise ValueError("version_id is required")
    return _contracting_child_key(case_id, f"BUDGET#{vid}")


def supporting_doc_key(case_id: str, doc_id: str) -> dict[str, str]:
    did = str(doc_id or "").strip()
    if not did:
        raise ValueError("doc_id is required")
    return _contracting_child_key(case_id, f"SUPPORT_DOC#{did}")


def client_package_key(case_id: str, package_id: str) -> dict[str, str]:
    pid = str(package_id or "").strip()
    if not pid:
        raise ValueError("package_id is required")
    return _contracting_child_key(case_id, f"PACKAGE#{pid}")


def esign_envelope_key(case_id: str, envelope_id: str) -> dict[str, str]:
    eid = str(envelope_id or "").strip()
    if not eid:
        raise ValueError("envelope_id is required")
    return _contracting_child_key(case_id, f"ESIGN#{eid}")


# -----------------------------
# Normalization
# -----------------------------


def _strip_db_fields(obj: dict[str, Any]) -> dict[str, Any]:
    out = dict(obj)
    for k in ("pk", "sk", "gsi1pk", "gsi1sk", "entityType"):
        out.pop(k, None)
    return out


def normalize_contracting_case(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if not item:
        return None
    out = _strip_db_fields(item)
    out["_id"] = str(item.get("caseId") or "").strip() or None
    return out


def normalize_contract_template(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if not item:
        return None
    out = _strip_db_fields(item)
    out["_id"] = str(item.get("templateId") or "").strip() or None
    return out


def normalize_contract_template_version(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if not item:
        return None
    out = _strip_db_fields(item)
    out["_id"] = str(item.get("versionId") or "").strip() or None
    return out


def normalize_contract_doc_version(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if not item:
        return None
    out = _strip_db_fields(item)
    out["_id"] = str(item.get("versionId") or "").strip() or None
    return out


def normalize_budget_version(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if not item:
        return None
    out = _strip_db_fields(item)
    out["_id"] = str(item.get("versionId") or "").strip() or None
    return out


def normalize_supporting_doc(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if not item:
        return None
    out = _strip_db_fields(item)
    out["_id"] = str(item.get("docId") or "").strip() or None
    return out


def normalize_client_package(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if not item:
        return None
    out = _strip_db_fields(item)
    out["_id"] = str(item.get("packageId") or "").strip() or None
    # Never return token hash
    out.pop("portalTokenHash", None)
    return out


def normalize_esign_envelope(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if not item:
        return None
    out = _strip_db_fields(item)
    out["_id"] = str(item.get("envelopeId") or "").strip() or None
    return out


# -----------------------------
# Contracting cases
# -----------------------------


def get_case_by_id(case_id: str) -> dict[str, Any] | None:
    it = get_main_table().get_item(key=contracting_case_key(case_id))
    return normalize_contracting_case(it)


def get_case_by_proposal_id(proposal_id: str) -> dict[str, Any] | None:
    pid = str(proposal_id or "").strip()
    if not pid:
        return None
    pg = get_main_table().query_page(
        index_name="GSI1",
        key_condition_expression=Key("gsi1pk").eq(contracting_case_gsi_pk(pid)),
        scan_index_forward=False,
        limit=1,
        next_token=None,
    )
    for it in pg.items or []:
        norm = normalize_contracting_case(it)
        if norm:
            return norm
    return None


def create_case(
    *,
    proposal_id: str,
    rfp_id: str,
    company_id: str | None,
    created_by_user_sub: str | None,
) -> dict[str, Any]:
    case_id = _new_id("contracting")
    now = _now_iso()
    item: dict[str, Any] = {
        **contracting_case_key(case_id),
        "entityType": "ContractingCase",
        "caseId": case_id,
        "proposalId": str(proposal_id).strip(),
        "rfpId": str(rfp_id).strip(),
        "companyId": str(company_id).strip() if company_id else None,
        "status": "draft",
        "keyTerms": {},
        "keyTermsRawJson": None,
        "owners": {"ownerUserSub": str(created_by_user_sub).strip() if created_by_user_sub else None},
        "audit": [{"event": "created", "at": now, "by": str(created_by_user_sub).strip() if created_by_user_sub else None}],
        "createdAt": now,
        "updatedAt": now,
        "gsi1pk": contracting_case_gsi_pk(str(proposal_id)),
        "gsi1sk": f"{now}#{case_id}",
    }
    get_main_table().put_item(item=item, condition_expression="attribute_not_exists(pk)")
    return normalize_contracting_case(item) or {}


def touch_case(case_id: str) -> dict[str, Any] | None:
    now = _now_iso()
    updated = get_main_table().update_item(
        key=contracting_case_key(case_id),
        update_expression="SET updatedAt = :u, gsi1sk = :g",
        expression_attribute_names=None,
        expression_attribute_values={":u": now, ":g": f"{now}#{str(case_id)}"},
        return_values="ALL_NEW",
    )
    return normalize_contracting_case(updated)


def update_case(case_id: str, patch: dict[str, Any], *, updated_by_user_sub: str | None) -> dict[str, Any] | None:
    allowed = {"status", "keyTerms", "keyTermsRawJson", "owners", "notes"}
    updates = {k: v for k, v in (patch or {}).items() if k in allowed}
    now = _now_iso()
    expr_parts: list[str] = []
    names: dict[str, str] = {}
    values: dict[str, Any] = {":u": now, ":g": f"{now}#{str(case_id)}"}
    i = 0
    for k, v in updates.items():
        i += 1
        nk = f"#k{i}"
        vk = f":v{i}"
        names[nk] = k
        values[vk] = v
        expr_parts.append(f"{nk} = {vk}")
    expr_parts.append("updatedAt = :u")
    expr_parts.append("gsi1sk = :g")
    if updated_by_user_sub:
        # Best-effort audit trail append
        expr_parts.append("audit = list_append(if_not_exists(audit, :empty), :evt)")
        values[":empty"] = []
        values[":evt"] = [{"event": "updated", "at": now, "by": str(updated_by_user_sub).strip()}]
    updated = get_main_table().update_item(
        key=contracting_case_key(case_id),
        update_expression="SET " + ", ".join(expr_parts),
        expression_attribute_names=names if names else None,
        expression_attribute_values=values,
        return_values="ALL_NEW",
    )
    return normalize_contracting_case(updated)


# -----------------------------
# Contract templates
# -----------------------------


def list_contract_templates(limit: int = 200, next_token: str | None = None) -> dict[str, Any]:
    pg = get_main_table().query_page(
        index_name="GSI1",
        key_condition_expression=Key("gsi1pk").eq(_type_pk("CONTRACT_TEMPLATE")),
        scan_index_forward=False,
        limit=max(1, min(500, int(limit or 200))),
        next_token=next_token,
    )
    out: list[dict[str, Any]] = []
    for it in pg.items or []:
        norm = normalize_contract_template(it)
        if norm:
            out.append(norm)
    return {"data": out, "nextToken": pg.next_token}


def create_contract_template(*, name: str, kind: str, created_by_user_sub: str | None) -> dict[str, Any]:
    template_id = _new_id("contract_template")
    now = _now_iso()
    item: dict[str, Any] = {
        **contract_template_key(template_id),
        "entityType": "ContractTemplate",
        "templateId": template_id,
        "name": str(name or "").strip() or "Contract Template",
        "kind": str(kind or "").strip().lower() or "combined",
        "currentVersionId": None,
        "createdAt": now,
        "updatedAt": now,
        "createdByUserSub": str(created_by_user_sub).strip() if created_by_user_sub else None,
        "gsi1pk": _type_pk("CONTRACT_TEMPLATE"),
        "gsi1sk": f"{now}#{template_id}",
    }
    get_main_table().put_item(item=item, condition_expression="attribute_not_exists(pk)")
    return normalize_contract_template(item) or {}


def add_contract_template_version(
    *,
    template_id: str,
    version_id: str | None = None,
    s3_key: str,
    sha256: str | None,
    variables_schema: dict[str, Any] | None,
    changelog: str | None,
    created_by_user_sub: str | None,
) -> dict[str, Any]:
    version_id = str(version_id or "").strip() or _new_id("ctv")
    now = _now_iso()
    version_item: dict[str, Any] = {
        **contract_template_version_key(template_id, version_id),
        "entityType": "ContractTemplateVersion",
        "templateId": str(template_id).strip(),
        "versionId": version_id,
        "s3Key": str(s3_key).strip(),
        "sha256": str(sha256).strip().lower() if sha256 else None,
        "variablesSchema": variables_schema if isinstance(variables_schema, dict) else {},
        "changelog": str(changelog).strip() if changelog else "",
        "createdByUserSub": str(created_by_user_sub).strip() if created_by_user_sub else None,
        "createdAt": now,
    }

    # Transactionally write version and update currentVersionId on template.
    t = get_main_table()
    t.transact_write(
        puts=[
            t.tx_put(
                item=version_item,
                condition_expression="attribute_not_exists(pk) AND attribute_not_exists(sk)",
            )
        ],
        updates=[
            t.tx_update(
                key=contract_template_key(template_id),
                update_expression="SET currentVersionId = :v, updatedAt = :u, gsi1sk = :g",
                expression_attribute_names=None,
                expression_attribute_values={
                    ":v": version_id,
                    ":u": now,
                    ":g": f"{now}#{str(template_id).strip()}",
                },
                condition_expression="attribute_exists(pk)",
            )
        ],
    )
    return normalize_contract_template_version(version_item) or {}


def get_contract_template(template_id: str) -> dict[str, Any] | None:
    it = get_main_table().get_item(key=contract_template_key(template_id))
    return normalize_contract_template(it)


def set_contract_template_current_version(
    *, template_id: str, version_id: str, updated_by_user_sub: str | None
) -> dict[str, Any] | None:
    tid = str(template_id or "").strip()
    vid = str(version_id or "").strip()
    if not tid:
        raise ValueError("template_id is required")
    if not vid:
        raise ValueError("version_id is required")
    now = _now_iso()
    # Ensure the version exists (prevents pointing at non-existent versions).
    if not get_contract_template_version(tid, vid):
        raise ValueError("Template version not found")
    expr = "SET currentVersionId = :v, updatedAt = :u, gsi1sk = :g"
    values: dict[str, Any] = {":v": vid, ":u": now, ":g": f"{now}#{tid}"}
    updated = get_main_table().update_item(
        key=contract_template_key(tid),
        update_expression=expr,
        expression_attribute_names=None,
        expression_attribute_values=values,
        condition_expression="attribute_exists(pk)",
        return_values="ALL_NEW",
    )
    return normalize_contract_template(updated)


def list_contract_template_versions(template_id: str, limit: int = 50) -> list[dict[str, Any]]:
    tid = str(template_id or "").strip()
    if not tid:
        return []
    pg = get_main_table().query_page(
        key_condition_expression=Key("pk").eq(f"CONTRACT_TEMPLATE#{tid}") & Key("sk").begins_with("VERSION#"),
        scan_index_forward=False,
        limit=max(1, min(200, int(limit or 50))),
        next_token=None,
    )
    out: list[dict[str, Any]] = []
    for it in pg.items or []:
        norm = normalize_contract_template_version(it)
        if norm:
            out.append(norm)
    return out


def get_contract_template_version(template_id: str, version_id: str) -> dict[str, Any] | None:
    it = get_main_table().get_item(key=contract_template_version_key(template_id, version_id))
    return normalize_contract_template_version(it)


# -----------------------------
# Contract document versions
# -----------------------------


def add_contract_doc_version(
    *,
    case_id: str,
    source_template_id: str | None,
    source_template_version_id: str | None,
    render_inputs: dict[str, Any] | None,
    docx_s3_key: str,
    pdf_s3_key: str | None,
    created_by_user_sub: str | None,
) -> dict[str, Any]:
    version_id = _new_id("contract_doc")
    now = _now_iso()
    item: dict[str, Any] = {
        **contract_doc_version_key(case_id, version_id),
        "entityType": "ContractDocumentVersion",
        "caseId": str(case_id).strip(),
        "versionId": version_id,
        "sourceTemplateId": str(source_template_id).strip() if source_template_id else None,
        "sourceTemplateVersionId": str(source_template_version_id).strip() if source_template_version_id else None,
        "renderInputs": render_inputs if isinstance(render_inputs, dict) else {},
        "docxS3Key": str(docx_s3_key).strip(),
        "pdfS3Key": str(pdf_s3_key).strip() if pdf_s3_key else None,
        "status": "generated",
        "createdAt": now,
        "createdByUserSub": str(created_by_user_sub).strip() if created_by_user_sub else None,
    }
    get_main_table().put_item(item=item, condition_expression="attribute_not_exists(pk) AND attribute_not_exists(sk)")
    # Touch parent case updatedAt
    try:
        touch_case(str(case_id))
    except Exception:
        pass
    return normalize_contract_doc_version(item) or {}


def list_contract_doc_versions(case_id: str, limit: int = 50) -> list[dict[str, Any]]:
    cid = str(case_id or "").strip()
    if not cid:
        return []
    pg = get_main_table().query_page(
        key_condition_expression=Key("pk").eq(f"CONTRACTING#{cid}") & Key("sk").begins_with("CONTRACT_DOC#"),
        scan_index_forward=False,
        limit=max(1, min(200, int(limit or 50))),
        next_token=None,
    )
    out: list[dict[str, Any]] = []
    for it in pg.items or []:
        norm = normalize_contract_doc_version(it)
        if norm:
            out.append(norm)
    return out


def get_contract_doc_version(case_id: str, version_id: str) -> dict[str, Any] | None:
    it = get_main_table().get_item(key=contract_doc_version_key(case_id, version_id))
    return normalize_contract_doc_version(it)


# -----------------------------
# Budget versions
# -----------------------------


def add_budget_version(
    *,
    case_id: str,
    budget_model: dict[str, Any],
    xlsx_s3_key: str,
    created_by_user_sub: str | None,
) -> dict[str, Any]:
    version_id = _new_id("budget")
    now = _now_iso()
    item: dict[str, Any] = {
        **budget_version_key(case_id, version_id),
        "entityType": "BudgetVersion",
        "caseId": str(case_id).strip(),
        "versionId": version_id,
        "budgetModel": budget_model if isinstance(budget_model, dict) else {},
        "xlsxS3Key": str(xlsx_s3_key).strip(),
        "createdAt": now,
        "createdByUserSub": str(created_by_user_sub).strip() if created_by_user_sub else None,
    }
    get_main_table().put_item(item=item, condition_expression="attribute_not_exists(pk) AND attribute_not_exists(sk)")
    try:
        touch_case(str(case_id))
    except Exception:
        pass
    return normalize_budget_version(item) or {}


def list_budget_versions(case_id: str, limit: int = 50) -> list[dict[str, Any]]:
    cid = str(case_id or "").strip()
    if not cid:
        return []
    pg = get_main_table().query_page(
        key_condition_expression=Key("pk").eq(f"CONTRACTING#{cid}") & Key("sk").begins_with("BUDGET#"),
        scan_index_forward=False,
        limit=max(1, min(200, int(limit or 50))),
        next_token=None,
    )
    out: list[dict[str, Any]] = []
    for it in pg.items or []:
        norm = normalize_budget_version(it)
        if norm:
            out.append(norm)
    return out


def get_budget_version(case_id: str, version_id: str) -> dict[str, Any] | None:
    it = get_main_table().get_item(key=budget_version_key(case_id, version_id))
    return normalize_budget_version(it)


# -----------------------------
# Supporting docs
# -----------------------------


def add_supporting_doc(
    *,
    case_id: str,
    doc_id: str | None = None,
    kind: str,
    required: bool,
    file_name: str,
    content_type: str,
    s3_key: str,
    expires_at: str | None,
    uploaded_by_user_sub: str | None,
) -> dict[str, Any]:
    doc_id = str(doc_id or "").strip() or _new_id("support_doc")
    now = _now_iso()
    item: dict[str, Any] = {
        **supporting_doc_key(case_id, doc_id),
        "entityType": "SupportingDoc",
        "caseId": str(case_id).strip(),
        "docId": doc_id,
        "kind": str(kind or "").strip().lower() or "other",
        "required": bool(required),
        "status": "uploaded",
        "fileName": str(file_name or "").strip() or "document",
        "contentType": str(content_type or "").strip().lower() or "application/octet-stream",
        "s3Key": str(s3_key).strip(),
        "expiresAt": str(expires_at).strip() if expires_at else None,
        "uploadedAt": now,
        "uploadedByUserSub": str(uploaded_by_user_sub).strip() if uploaded_by_user_sub else None,
    }
    get_main_table().put_item(item=item, condition_expression="attribute_not_exists(pk) AND attribute_not_exists(sk)")
    try:
        touch_case(str(case_id))
    except Exception:
        pass
    return normalize_supporting_doc(item) or {}


def list_supporting_docs(case_id: str, limit: int = 200) -> list[dict[str, Any]]:
    cid = str(case_id or "").strip()
    if not cid:
        return []
    pg = get_main_table().query_page(
        key_condition_expression=Key("pk").eq(f"CONTRACTING#{cid}") & Key("sk").begins_with("SUPPORT_DOC#"),
        scan_index_forward=False,
        limit=max(1, min(500, int(limit or 200))),
        next_token=None,
    )
    out: list[dict[str, Any]] = []
    for it in pg.items or []:
        norm = normalize_supporting_doc(it)
        if norm:
            out.append(norm)
    return out


# -----------------------------
# Client package + portal tokens
# -----------------------------


def _portal_pepper() -> str:
    raw = settings.canva_token_enc_key or settings.jwt_secret
    if not raw:
        # In production, settings.require_in_production enforces this.
        raise RuntimeError("Missing CANVA_TOKEN_ENC_KEY (or JWT_SECRET) for portal token hashing")
    return str(raw)


def new_portal_token(num_bytes: int = 32) -> str:
    b = os.urandom(max(16, min(64, int(num_bytes or 32))))
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")


def hash_portal_token(token: str) -> str:
    t = str(token or "").strip()
    if not t:
        raise ValueError("token is required")
    pepper = _portal_pepper().encode("utf-8")
    h = hashlib.sha256()
    h.update(pepper)
    h.update(b"\n")
    h.update(t.encode("utf-8"))
    return h.hexdigest()


def create_client_package(
    *,
    case_id: str,
    name: str | None,
    selected_files: list[dict[str, Any]] | None,
    created_by_user_sub: str | None,
) -> dict[str, Any]:
    package_id = _new_id("package")
    now = _now_iso()
    item: dict[str, Any] = {
        **client_package_key(case_id, package_id),
        "entityType": "ClientPackage",
        "caseId": str(case_id).strip(),
        "packageId": package_id,
        "name": str(name or "").strip() or "Client package",
        "selectedFiles": selected_files if isinstance(selected_files, list) else [],
        "publishedAt": None,
        "revokedAt": None,
        "portalTokenHash": None,
        "portalTokenExpiresAt": None,
        "createdAt": now,
        "updatedAt": now,
        "createdByUserSub": str(created_by_user_sub).strip() if created_by_user_sub else None,
    }
    get_main_table().put_item(item=item, condition_expression="attribute_not_exists(pk) AND attribute_not_exists(sk)")
    try:
        touch_case(str(case_id))
    except Exception:
        pass
    return normalize_client_package(item) or {}


def list_client_packages(case_id: str, limit: int = 100) -> list[dict[str, Any]]:
    cid = str(case_id or "").strip()
    if not cid:
        return []
    pg = get_main_table().query_page(
        key_condition_expression=Key("pk").eq(f"CONTRACTING#{cid}") & Key("sk").begins_with("PACKAGE#"),
        scan_index_forward=False,
        limit=max(1, min(500, int(limit or 100))),
        next_token=None,
    )
    out: list[dict[str, Any]] = []
    for it in pg.items or []:
        norm = normalize_client_package(it)
        if norm:
            out.append(norm)
    return out


def get_client_package(*, case_id: str, package_id: str) -> dict[str, Any] | None:
    cid = str(case_id or "").strip()
    pid = str(package_id or "").strip()
    if not cid or not pid:
        return None
    it = get_main_table().get_item(key=client_package_key(cid, pid))
    return normalize_client_package(it)


def publish_client_package(
    *,
    case_id: str,
    package_id: str,
    token_ttl_days: int = 14,
    published_by_user_sub: str | None,
) -> dict[str, Any]:
    now = _now_iso()
    # Keep portal links short-lived by default; clamp for safety.
    ttl_days = max(1, min(30, int(token_ttl_days or 7)))
    expires_at = (datetime.now(timezone.utc) + timedelta(days=ttl_days)).isoformat().replace("+00:00", "Z")
    token = new_portal_token()
    token_hash = hash_portal_token(token)

    # Make package discoverable by token via GSI1.
    updated = get_main_table().update_item(
        key=client_package_key(case_id, package_id),
        update_expression=(
            "SET publishedAt = :p, updatedAt = :u, portalTokenHash = :h, portalTokenExpiresAt = :e, "
            "gsi1pk = :gpk, gsi1sk = :gsk"
        ),
        expression_attribute_names=None,
        expression_attribute_values={
            ":p": now,
            ":u": now,
            ":h": token_hash,
            ":e": expires_at,
            ":gpk": f"PORTAL_TOKEN#{token_hash}",
            ":gsk": f"{now}#{package_id}",
        },
        return_values="ALL_NEW",
    )
    if not updated:
        raise DdbNotFound(message="Package not found", operation="UpdateItem", table_name=get_main_table().table_name, key=client_package_key(case_id, package_id))
    try:
        touch_case(str(case_id))
    except Exception:
        pass
    out = normalize_client_package(updated) or {}
    out["portalToken"] = token  # Only returned on publish.
    return out


def rotate_client_package_token(
    *,
    case_id: str,
    package_id: str,
    token_ttl_days: int = 7,
    rotated_by_user_sub: str | None,
) -> dict[str, Any]:
    """
    Mint a new portal token for an already-published package (token rotation).
    Returns the new token in `portalToken`.
    """
    cid = str(case_id or "").strip()
    pid = str(package_id or "").strip()
    if not cid or not pid:
        raise ValueError("case_id and package_id are required")

    now = _now_iso()
    ttl_days = max(1, min(30, int(token_ttl_days or 7)))
    expires_at = (datetime.now(timezone.utc) + timedelta(days=ttl_days)).isoformat().replace("+00:00", "Z")
    token = new_portal_token()
    token_hash = hash_portal_token(token)

    updated = get_main_table().update_item(
        key=client_package_key(cid, pid),
        update_expression=(
            "SET updatedAt = :u, portalTokenHash = :h, portalTokenExpiresAt = :e, "
            "gsi1pk = :gpk, gsi1sk = :gsk REMOVE revokedAt"
        ),
        expression_attribute_names=None,
        expression_attribute_values={
            ":u": now,
            ":h": token_hash,
            ":e": expires_at,
            ":gpk": f"PORTAL_TOKEN#{token_hash}",
            ":gsk": f"{now}#{pid}",
        },
        return_values="ALL_NEW",
    )
    if not updated:
        raise DdbNotFound(message="Package not found", operation="UpdateItem", table_name=get_main_table().table_name, key=client_package_key(cid, pid))
    out = normalize_client_package(updated) or {}
    out["portalToken"] = token
    return out


def revoke_client_package(*, case_id: str, package_id: str, revoked_by_user_sub: str | None) -> dict[str, Any]:
    now = _now_iso()
    updated = get_main_table().update_item(
        key=client_package_key(case_id, package_id),
        update_expression=(
            "SET revokedAt = :r, updatedAt = :u, portalTokenHash = :n, portalTokenExpiresAt = :n "
            "REMOVE gsi1pk, gsi1sk"
        ),
        expression_attribute_names=None,
        expression_attribute_values={":r": now, ":u": now, ":n": None},
        return_values="ALL_NEW",
    )
    out = normalize_client_package(updated) or None
    try:
        touch_case(str(case_id))
    except Exception:
        pass
    return out


def get_package_by_portal_token(token: str) -> dict[str, Any] | None:
    tok = str(token or "").strip()
    if not tok:
        return None
    h = hash_portal_token(tok)
    pg = get_main_table().query_page(
        index_name="GSI1",
        key_condition_expression=Key("gsi1pk").eq(f"PORTAL_TOKEN#{h}"),
        scan_index_forward=False,
        limit=1,
        next_token=None,
    )
    for it in pg.items or []:
        # Validate expiry + revoked on read too
        revoked = str(it.get("revokedAt") or "").strip()
        if revoked:
            return None
        exp = str(it.get("portalTokenExpiresAt") or "").strip()
        if exp:
            try:
                dt = datetime.fromisoformat(exp.replace("Z", "+00:00"))
                if dt <= datetime.now(timezone.utc):
                    return None
            except Exception:
                # If malformed expiry, fail closed.
                return None
        return normalize_client_package(it)
    return None


# -----------------------------
# E-sign envelopes (stub metadata storage)
# -----------------------------


def create_esign_envelope(
    *,
    case_id: str,
    provider: str,
    recipients: list[dict[str, Any]] | None,
    files: list[dict[str, Any]] | None,
    created_by_user_sub: str | None,
) -> dict[str, Any]:
    envelope_id = _new_id("envelope")
    now = _now_iso()
    item: dict[str, Any] = {
        **esign_envelope_key(case_id, envelope_id),
        "entityType": "ESignEnvelope",
        "caseId": str(case_id).strip(),
        "envelopeId": envelope_id,
        "provider": str(provider or "stub").strip().lower() or "stub",
        "status": "draft",
        "recipients": recipients if isinstance(recipients, list) else [],
        "files": files if isinstance(files, list) else [],
        "providerMeta": {},
        "createdAt": now,
        "updatedAt": now,
        "sentAt": None,
        "completedAt": None,
        "createdByUserSub": str(created_by_user_sub).strip() if created_by_user_sub else None,
    }
    get_main_table().put_item(item=item, condition_expression="attribute_not_exists(pk) AND attribute_not_exists(sk)")
    try:
        touch_case(str(case_id))
    except Exception:
        pass
    return normalize_esign_envelope(item) or {}


def update_esign_envelope(case_id: str, envelope_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
    allowed = {"status", "providerMeta", "sentAt", "completedAt", "recipients", "files"}
    updates = {k: v for k, v in (patch or {}).items() if k in allowed}
    if not updates:
        it = get_main_table().get_item(key=esign_envelope_key(case_id, envelope_id))
        return normalize_esign_envelope(it)
    now = _now_iso()
    expr_parts: list[str] = []
    names: dict[str, str] = {}
    values: dict[str, Any] = {":u": now}
    i = 0
    for k, v in updates.items():
        i += 1
        nk = f"#k{i}"
        vk = f":v{i}"
        names[nk] = k
        values[vk] = v
        expr_parts.append(f"{nk} = {vk}")
    expr_parts.append("updatedAt = :u")
    updated = get_main_table().update_item(
        key=esign_envelope_key(case_id, envelope_id),
        update_expression="SET " + ", ".join(expr_parts),
        expression_attribute_names=names if names else None,
        expression_attribute_values=values,
        return_values="ALL_NEW",
    )
    return normalize_esign_envelope(updated)


def list_esign_envelopes(case_id: str, limit: int = 50) -> list[dict[str, Any]]:
    cid = str(case_id or "").strip()
    if not cid:
        return []
    pg = get_main_table().query_page(
        key_condition_expression=Key("pk").eq(f"CONTRACTING#{cid}") & Key("sk").begins_with("ESIGN#"),
        scan_index_forward=False,
        limit=max(1, min(200, int(limit or 50))),
        next_token=None,
    )
    out: list[dict[str, Any]] = []
    for it in pg.items or []:
        norm = normalize_esign_envelope(it)
        if norm:
            out.append(norm)
    return out


def get_esign_envelope(case_id: str, envelope_id: str) -> dict[str, Any] | None:
    it = get_main_table().get_item(key=esign_envelope_key(case_id, envelope_id))
    return normalize_esign_envelope(it)

