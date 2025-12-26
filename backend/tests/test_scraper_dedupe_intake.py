from __future__ import annotations

from typing import Any

import pytest


class FakeTable:
    """
    Minimal in-memory stand-in for DynamoTable used by repositories.

    This is intentionally tiny: just enough to validate dedupe + intake upserts
    without needing real DynamoDB.
    """

    def __init__(self):
        # Keyed by (pk, sk)
        self.items: dict[tuple[str, str], dict[str, Any]] = {}

    def get_item(self, *, key: dict[str, Any]) -> dict[str, Any] | None:
        pk = str(key.get("pk") or "")
        sk = str(key.get("sk") or "")
        return self.items.get((pk, sk))

    def put_item(self, *, item: dict[str, Any], condition_expression: str | None = None, **_kw) -> dict[str, Any]:
        from app.db.dynamodb.errors import DdbConflict

        pk = str(item.get("pk") or "")
        sk = str(item.get("sk") or "")
        if condition_expression and "attribute_not_exists(pk)" in condition_expression:
            if (pk, sk) in self.items:
                raise DdbConflict(message="conflict", operation="PutItem", table_name="Fake", key={"pk": pk, "sk": sk})
        self.items[(pk, sk)] = dict(item)
        return {"ok": True}

    # --- transactions (used by dedupe) ---
    def tx_put(self, *, item: dict[str, Any], condition_expression: str | None = None, **_kw) -> dict[str, Any]:
        return {"Item": item, "ConditionExpression": condition_expression}

    def transact_write(self, *, puts=(), deletes=(), updates=(), **_kw) -> dict[str, Any]:
        from app.db.dynamodb.errors import DdbConflict

        # Apply puts in order; if any conditional fails, raise DdbConflict (good enough for unit tests)
        for p in puts:
            item = dict(p.get("Item") or {})
            cond = p.get("ConditionExpression")
            pk = str(item.get("pk") or "")
            sk = str(item.get("sk") or "")
            if cond and "attribute_not_exists(pk)" in cond:
                if (pk, sk) in self.items:
                    raise DdbConflict(message="conflict", operation="TransactWriteItems", table_name="Fake", key={"pk": pk, "sk": sk})
            self.items[(pk, sk)] = dict(item)
        return {"ok": True}

    def update_item(
        self,
        *,
        key: dict[str, Any],
        update_expression: str,
        expression_attribute_names: dict[str, str] | None,
        expression_attribute_values: dict[str, Any],
        **_kw,
    ) -> dict[str, Any]:
        pk = str(key.get("pk") or "")
        sk = str(key.get("sk") or "")
        cur = dict(self.items.get((pk, sk)) or {"pk": pk, "sk": sk})

        # Super-minimal parser: supports "SET a = :x, b = :y, ..."
        assert update_expression.startswith("SET ")
        assigns = update_expression[len("SET ") :].split(",")

        # Resolve attribute names (e.g. #s => status)
        def name(n: str) -> str:
            n = n.strip()
            if n.startswith("#") and expression_attribute_names:
                return str(expression_attribute_names.get(n) or n)
            return n

        for a in assigns:
            left, right = a.split("=", 1)
            left = name(left)
            right = right.strip()
            if right.startswith("if_not_exists("):
                # Handle: createdAt = if_not_exists(createdAt, :ca)
                inner = right[len("if_not_exists(") :].rstrip(")")
                fld, tok = [x.strip() for x in inner.split(",", 1)]
                if fld not in cur or cur.get(fld) is None:
                    cur[left] = expression_attribute_values.get(tok)
                continue
            cur[left] = expression_attribute_values.get(right)

        self.items[(pk, sk)] = cur
        return cur


@pytest.fixture()
def fake_table(monkeypatch):
    t = FakeTable()
    # Patch both modules that use get_main_table() directly.
    import app.repositories.rfp_scraped_rfps_repo as scraped_repo
    import app.repositories.rfp_intake_queue_repo as intake_repo

    monkeypatch.setattr(scraped_repo, "get_main_table", lambda: t)
    monkeypatch.setattr(intake_repo, "get_main_table", lambda: t)
    return t


def test_scraped_candidate_dedup_creates_single_candidate_and_intake(fake_table):
    import app.repositories.rfp_scraped_rfps_repo as scraped_repo

    c1, created1 = scraped_repo.create_scraped_rfp_deduped(
        source="planning.org",
        source_url="https://www.planning.org/consultants/rfp/search/",
        title="Test RFP",
        detail_url="https://www.planning.org/consultants/rfp/123/",
        metadata={"x": 1},
    )
    assert created1 is True
    assert c1.get("_id")

    c2, created2 = scraped_repo.create_scraped_rfp_deduped(
        source="planning.org",
        source_url="https://www.planning.org/consultants/rfp/search/",
        title="Test RFP (duplicate title change)",
        detail_url="https://www.planning.org/consultants/rfp/123",  # normalized
        metadata={"x": 2},
    )
    assert created2 is False
    assert c2.get("_id") == c1.get("_id")

    # Intake item exists
    intake_key = ("RFPINTAKE#" + c1["_id"], "ITEM")
    assert intake_key in fake_table.items


def test_update_candidate_status_updates_intake_status(fake_table):
    import app.repositories.rfp_scraped_rfps_repo as scraped_repo

    c, created = scraped_repo.create_scraped_rfp_deduped(
        source="custom",
        source_url="https://example.com/list",
        title="Example",
        detail_url="https://example.com/rfp/1",
        metadata={},
    )
    assert created is True
    cid = str(c["_id"])

    # Mark skipped -> should upsert intake with status=skipped
    updated = scraped_repo.update_scraped_rfp(cid, {"status": "skipped"})
    assert updated and updated.get("status") == "skipped"

    intake = fake_table.items.get(("RFPINTAKE#" + cid, "ITEM")) or {}
    assert intake.get("status") == "skipped"


