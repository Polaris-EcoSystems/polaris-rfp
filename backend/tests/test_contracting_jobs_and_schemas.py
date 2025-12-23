from __future__ import annotations


def test_validate_key_terms_returns_field_errors():
    from app.domain.pipeline.contracting.contracting_schemas import validate_key_terms

    # Invalid severity should produce a structured error.
    norm, errs = validate_key_terms(
        {
            "riskMitigations": [
                {"risk": "Schedule slip", "severity": "extreme", "mitigation": "Buffer time"}
            ]
        }
    )
    assert norm == {}
    assert errs
    assert any("riskMitigations" in ".".join(e.get("loc") or []) for e in errs)


def test_contracting_job_idempotency_returns_same_job(monkeypatch):
    from app.db.dynamodb.errors import DdbConflict
    from app.repositories.contracting import contracting_jobs_repo

    class FakeTable:
        table_name = "fake"

        def __init__(self):
            self._items: dict[tuple[str, str], dict] = {}

        def get_item(self, key: dict):
            k = (str(key.get("pk")), str(key.get("sk")))
            it = self._items.get(k)
            return dict(it) if it else None

        def tx_put(self, *, item: dict, condition_expression: str | None = None):
            return {"item": item, "condition": condition_expression}

        def transact_write(self, *, puts=None, updates=None):
            puts = puts or []
            for p in puts:
                item = p.get("item") or {}
                pk = str(item.get("pk"))
                sk = str(item.get("sk"))
                k = (pk, sk)
                if k in self._items:
                    raise DdbConflict(message="conflict", operation="PutItem", table_name=self.table_name)
            for p in puts:
                item = p.get("item") or {}
                k = (str(item.get("pk")), str(item.get("sk")))
                self._items[k] = dict(item)

    ft = FakeTable()
    monkeypatch.setattr(contracting_jobs_repo, "get_main_table", lambda: ft)

    j1 = contracting_jobs_repo.create_job(
        idempotency_key="same-key",
        job_type="contract_generate",
        case_id="case_1",
        proposal_id="p1",
        requested_by_user_sub="u1",
        payload={"caseId": "case_1"},
    )
    j2 = contracting_jobs_repo.create_job(
        idempotency_key="same-key",
        job_type="contract_generate",
        case_id="case_1",
        proposal_id="p1",
        requested_by_user_sub="u1",
        payload={"caseId": "case_1"},
    )

    assert j1.get("jobId")
    assert j2.get("jobId") == j1.get("jobId")

