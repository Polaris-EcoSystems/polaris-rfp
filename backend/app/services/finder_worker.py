from __future__ import annotations

import json
from typing import Any

from . import finder_repo
from .buyer_scoring import enrich_buyer_profile_with_ai, score_buyer_likelihood
from .linkedin_playwright import LinkedInSessionError, discover_people_for_company
from .rfps_repo import get_rfp_by_id
from .token_crypto import decrypt_string


def _load_storage_state_for_user(user_sub: str) -> dict[str, Any]:
    item = finder_repo.get_user_linkedin_state(user_sub=user_sub)
    if not item or not item.get("encryptedStorageState"):
        raise RuntimeError("LinkedIn storageState not configured for this user")
    raw = decrypt_string(item["encryptedStorageState"])
    if not raw:
        raise RuntimeError("LinkedIn storageState could not be decrypted")
    return json.loads(raw)


def run_finder_job(
    *,
    run_id: str,
    user_sub: str,
    rfp_id: str,
    company_name: str | None,
    company_linkedin_url: str | None,
    max_people: int,
    target_titles: list[str] | None,
    enrich_top_n: int = 6,
) -> None:
    try:
        finder_repo.update_run_fields(run_id, {"status": "running", "error": None})

        storage_state = _load_storage_state_for_user(user_sub)
        people = discover_people_for_company(
            storage_state=storage_state,
            company_name=company_name,
            company_linkedin_url=company_linkedin_url,
            max_people=max_people,
            headless=True,
        )

        finder_repo.update_run_fields(
            run_id,
            {"progress": {"discovered": len(people), "saved": 0, "scored": 0}},
        )

        scored: list[dict[str, Any]] = []
        for p in people:
            score, reasons = score_buyer_likelihood(
                title=str(p.get("title") or ""),
                target_titles=target_titles or [],
            )
            obj = dict(p)
            obj["buyerScore"] = score
            obj["buyerReasons"] = reasons
            scored.append(obj)

        scored.sort(key=lambda x: int(x.get("buyerScore") or 0), reverse=True)

        rfp = get_rfp_by_id(rfp_id)
        enriched: list[dict[str, Any]] = []
        for idx, p in enumerate(scored):
            if idx < max(0, int(enrich_top_n or 0)):
                try:
                    enriched.append(
                        enrich_buyer_profile_with_ai(
                            person=p,
                            company_name=company_name,
                            rfp=rfp,
                        )
                    )
                except Exception:
                    enriched.append(p)
            else:
                enriched.append(p)

        saved_n = finder_repo.put_profiles(run_id=run_id, profiles=enriched)
        finder_repo.update_run_fields(
            run_id,
            {
                "status": "done",
                "progress": {
                    "discovered": len(people),
                    "saved": saved_n,
                    "scored": len(enriched),
                },
            },
        )
    except LinkedInSessionError as e:
        finder_repo.update_run_fields(run_id, {"status": "error", "error": str(e)})
    except Exception as e:
        finder_repo.update_run_fields(run_id, {"status": "error", "error": str(e) or "Finder run failed"})


