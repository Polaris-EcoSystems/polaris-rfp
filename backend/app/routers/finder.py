from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Body, File, HTTPException, Request, UploadFile

from ..auth.cognito import VerifiedUser
from ..services import finder_repo
from ..services.finder_worker import run_finder_job
from ..services.linkedin_playwright import LinkedInSessionError, validate_linkedin_session
from ..repositories.rfp.rfps_repo import get_rfp_by_id, update_rfp
from ..services.token_crypto import decrypt_string, encrypt_string


router = APIRouter(tags=["finder"])


def _user_from_request(request: Request) -> VerifiedUser:
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return user


@router.get("/linkedin/storage-state/status")
def linkedin_storage_state_status(request: Request):
    user = _user_from_request(request)
    item = finder_repo.get_user_linkedin_state(user_sub=user.sub)
    return {"connected": bool(item and item.get("encryptedStorageState"))}


@router.get("/linkedin/session/validate")
def linkedin_session_validate(request: Request):
    user = _user_from_request(request)
    item = finder_repo.get_user_linkedin_state(user_sub=user.sub)
    if not item or not item.get("encryptedStorageState"):
        raise HTTPException(status_code=400, detail="LinkedIn storageState not configured for this user")

    raw = decrypt_string(item.get("encryptedStorageState"))
    if not raw:
        raise HTTPException(status_code=400, detail="LinkedIn storageState could not be decrypted")

    try:
        storage_state = finder_repo.normalize_storage_state(raw)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid LinkedIn storageState")

    try:
        validate_linkedin_session(storage_state=storage_state, headless=True)
        return {"ok": True}
    except LinkedInSessionError as e:
        return {"ok": False, "reason": str(e)}
    except Exception as e:
        return {"ok": False, "reason": str(e) or "Failed to validate LinkedIn session"}


@router.post("/linkedin/storage-state")
async def upload_linkedin_storage_state(
    request: Request,
    file: UploadFile | None = File(default=None),
    body: dict[str, Any] | None = Body(default=None),
):
    user = _user_from_request(request)

    raw: Any = None
    if file is not None:
        data = await file.read()
        try:
            raw = json.loads(data.decode("utf-8", errors="ignore"))
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON file: {e}")
    else:
        payload = body or {}
        raw = payload.get("storageState") if isinstance(payload, dict) else payload

    try:
        storage_state = finder_repo.normalize_storage_state(raw)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e) or "Invalid storageState")

    enc = encrypt_string(json.dumps(storage_state))
    if not enc:
        raise HTTPException(status_code=500, detail="Failed to encrypt storageState")

    finder_repo.put_user_linkedin_state(user_sub=user.sub, encrypted_storage_state=enc)
    return {"success": True, "connected": True}


@router.post("/runs", status_code=201)
def start_finder_run(
    request: Request,
    background: BackgroundTasks,
    body: dict[str, Any] = Body(...),
):
    user = _user_from_request(request)

    rfp_id = str((body or {}).get("rfpId") or "").strip()
    if not rfp_id:
        raise HTTPException(status_code=400, detail="rfpId is required")

    rfp = get_rfp_by_id(rfp_id)
    if not rfp:
        raise HTTPException(status_code=404, detail="RFP not found")

    company_name = (
        str((body or {}).get("companyName") or rfp.get("clientName") or "").strip() or None
    )
    company_linkedin_url = str((body or {}).get("companyLinkedInUrl") or "").strip() or None
    max_people = max(1, min(200, int((body or {}).get("maxPeople") or 50)))

    target_titles_in = (body or {}).get("targetTitles") or []
    target_titles = (
        [str(x).strip() for x in target_titles_in if str(x).strip()]
        if isinstance(target_titles_in, list)
        else []
    )

    run_id = finder_repo.new_id("run")
    run_item = finder_repo.create_run(
        run_id=run_id,
        rfp_id=rfp_id,
        user_sub=user.sub,
        company_name=company_name,
        company_linkedin_url=company_linkedin_url,
        max_people=max_people,
        target_titles=target_titles,
    )

    background.add_task(
        run_finder_job,
        run_id=run_id,
        user_sub=user.sub,
        rfp_id=rfp_id,
        company_name=company_name,
        company_linkedin_url=company_linkedin_url,
        max_people=max_people,
        target_titles=target_titles,
    )

    return {"runId": run_id, "run": run_item}


@router.get("/runs/{run_id}")
def get_finder_run(request: Request, run_id: str):
    _user_from_request(request)
    run = finder_repo.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.get("/runs/{run_id}/profiles")
def list_finder_profiles(request: Request, run_id: str, limit: int = 200):
    _user_from_request(request)
    return {"data": finder_repo.list_profiles(run_id, limit=limit)}


@router.post("/runs/{run_id}/save-to-rfp")
def save_top_buyers_to_rfp(
    request: Request,
    run_id: str,
    body: dict[str, Any] = Body(...),
):
    """
    Persist top buyer profiles onto the RFP record for easy access later.

    Body:
      - rfpId (required)
      - topN (optional, default 10)
      - mode (optional: "merge" | "overwrite", default "merge")
      - selected (optional: array of profileUrl/profileId strings to save)
    """
    _user_from_request(request)

    rfp_id = str((body or {}).get("rfpId") or "").strip()
    if not rfp_id:
        raise HTTPException(status_code=400, detail="rfpId is required")

    rfp = get_rfp_by_id(rfp_id)
    if not rfp:
        raise HTTPException(status_code=404, detail="RFP not found")

    top_n = int((body or {}).get("topN") or 10)
    top_n = max(1, min(50, top_n))

    mode = str((body or {}).get("mode") or "merge").strip().lower()
    if mode not in ("merge", "overwrite"):
        raise HTTPException(status_code=400, detail='mode must be "merge" or "overwrite"')

    items = finder_repo.list_profiles(run_id, limit=500)
    if not items:
        raise HTTPException(status_code=400, detail="No profiles found for this run")

    selected_in = (body or {}).get("selected")
    selected: list[str] = []
    if isinstance(selected_in, list):
        selected = [str(x or "").strip() for x in selected_in]
        selected = [x for x in selected if x]

    def score(x: Any) -> int:
        try:
            return int(x.get("buyerScore") or 0)
        except Exception:
            return 0

    items.sort(key=score, reverse=True)

    # Normalize + optionally merge into the RFP.
    chosen = items
    if selected:
        # Match selected tokens against profileUrl or profileId.
        selected_set = set([s.lower() for s in selected])

        def matches(p: dict[str, Any]) -> bool:
            pid = str(p.get("profileId") or "").strip().lower()
            url = str(p.get("profileUrl") or "").strip().lower()
            return bool((pid and pid in selected_set) or (url and url in selected_set))

        chosen = [p for p in items if isinstance(p, dict) and matches(p)]
    else:
        chosen = items[:top_n]

    incoming: list[dict[str, Any]] = []
    for p in chosen[:50]:
        incoming.append(
            {
                "profileId": p.get("profileId"),
                "profileUrl": p.get("profileUrl"),
                "name": p.get("name"),
                "title": p.get("title"),
                "location": p.get("location"),
                "buyerScore": p.get("buyerScore"),
                "buyerReasons": p.get("buyerReasons"),
                "ai": p.get("ai"),
                "sourceRunId": run_id,
            }
        )

    existing = (rfp or {}).get("buyerProfiles")
    if not isinstance(existing, list):
        existing = []

    def key(obj: dict[str, Any]) -> str:
        pu = str(obj.get("profileUrl") or "").strip()
        if pu:
            return f"url:{pu}"
        pid = str(obj.get("profileId") or "").strip()
        if pid:
            return f"id:{pid}"
        # last resort: name+title
        return f"nt:{str(obj.get('name') or '').strip()}|{str(obj.get('title') or '').strip()}"

    merged: dict[str, dict[str, Any]] = {}

    if mode == "merge":
        for e in existing:
            if isinstance(e, dict):
                merged[key(e)] = dict(e)

    for inc in incoming:
        k = key(inc)
        prev = merged.get(k) if mode == "merge" else None
        if prev:
            # Prefer new non-empty fields; keep higher score.
            out = dict(prev)
            for fld in ("profileId", "profileUrl", "name", "title", "location"):
                v = inc.get(fld)
                if v:
                    out[fld] = v
            # Prefer newest AI enrichment if present
            if inc.get("ai"):
                out["ai"] = inc.get("ai")
            # Buyer score/reasons: keep max
            try:
                out_score = int(out.get("buyerScore") or 0)
                in_score = int(inc.get("buyerScore") or 0)
                if in_score >= out_score:
                    out["buyerScore"] = inc.get("buyerScore")
                    out["buyerReasons"] = inc.get("buyerReasons")
            except Exception:
                out["buyerScore"] = inc.get("buyerScore")
                out["buyerReasons"] = inc.get("buyerReasons")
            out["sourceRunId"] = run_id
            merged[k] = out
        else:
            merged[k] = dict(inc)

    # Sort by buyerScore desc and cap to 50 saved profiles.
    merged_list = list(merged.values())
    merged_list.sort(key=lambda x: int(x.get("buyerScore") or 0), reverse=True)
    merged_list = merged_list[:50]

    updated = update_rfp(rfp_id, {"buyerProfiles": merged_list})
    return {
        "success": True,
        "saved": len(incoming),
        "total": len(merged_list),
        "mode": mode,
        "selected": len(selected),
        "rfp": updated,
    }




