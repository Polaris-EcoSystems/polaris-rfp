from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable

from boto3.dynamodb.types import TypeSerializer
from botocore.exceptions import ClientError

from .client import dynamodb_client, table_resource
from .errors import DdbInternal, DdbNotFound
from .pagination import decode_next_token, encode_next_token
from .retry import RetryPolicy, ddb_call


_serializer = TypeSerializer()


def _serialize_item(item: dict[str, Any]) -> dict[str, Any]:
    # DynamoDB client expects AttributeValue shape; TypeSerializer produces {'S': '...'} etc.
    return {k: _serializer.serialize(v) for k, v in item.items()}


@dataclass(slots=True)
class Page:
    items: list[dict[str, Any]]
    next_token: str | None


class DynamoTable:
    def __init__(self, *, table_name: str):
        self.table_name = str(table_name)
        self._table = table_resource(self.table_name)
        self._client = dynamodb_client()

    # --- basic operations ---

    def get_item(self, *, key: dict[str, Any]) -> dict[str, Any] | None:
        def _op():
            resp = self._table.get_item(Key=key)
            return resp.get("Item")

        return ddb_call("GetItem", _op, table_name=self.table_name, key=key)

    def get_required(self, *, key: dict[str, Any], message: str = "Item not found") -> dict[str, Any]:
        item = self.get_item(key=key)
        if not item:
            raise DdbNotFound(message=message, operation="GetItem", table_name=self.table_name, key=key)
        return item

    def put_item(
        self,
        *,
        item: dict[str, Any],
        condition_expression: str | None = None,
        expression_attribute_names: dict[str, str] | None = None,
        expression_attribute_values: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        def _op():
            kwargs: dict[str, Any] = {"Item": item}
            if condition_expression:
                kwargs["ConditionExpression"] = condition_expression
            if expression_attribute_names:
                kwargs["ExpressionAttributeNames"] = expression_attribute_names
            if expression_attribute_values:
                kwargs["ExpressionAttributeValues"] = expression_attribute_values
            return self._table.put_item(**kwargs)

        return ddb_call("PutItem", _op, table_name=self.table_name)

    def delete_item(
        self,
        *,
        key: dict[str, Any],
        condition_expression: str | None = None,
        expression_attribute_names: dict[str, str] | None = None,
        expression_attribute_values: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        def _op():
            kwargs: dict[str, Any] = {"Key": key}
            if condition_expression:
                kwargs["ConditionExpression"] = condition_expression
            if expression_attribute_names:
                kwargs["ExpressionAttributeNames"] = expression_attribute_names
            if expression_attribute_values:
                kwargs["ExpressionAttributeValues"] = expression_attribute_values
            return self._table.delete_item(**kwargs)

        return ddb_call("DeleteItem", _op, table_name=self.table_name, key=key)

    def update_item(
        self,
        *,
        key: dict[str, Any],
        update_expression: str,
        expression_attribute_names: dict[str, str] | None,
        expression_attribute_values: dict[str, Any],
        condition_expression: str | None = None,
        return_values: str = "ALL_NEW",
    ) -> dict[str, Any] | None:
        def _op():
            kwargs: dict[str, Any] = {
                "Key": key,
                "UpdateExpression": update_expression,
                "ExpressionAttributeValues": expression_attribute_values,
                "ReturnValues": return_values,
            }
            if expression_attribute_names:
                kwargs["ExpressionAttributeNames"] = expression_attribute_names
            if condition_expression:
                kwargs["ConditionExpression"] = condition_expression
            resp = self._table.update_item(**kwargs)
            return resp.get("Attributes")

        return ddb_call("UpdateItem", _op, table_name=self.table_name, key=key)

    # --- query/pagination ---

    def query_page(
        self,
        *,
        key_condition_expression: Any,
        index_name: str | None = None,
        limit: int = 50,
        scan_index_forward: bool = False,
        filter_expression: Any | None = None,
        next_token: str | None = None,
    ) -> Page:
        lim = max(1, min(500, int(limit or 50)))
        lek = decode_next_token(next_token) if next_token else None

        def _op():
            kwargs: dict[str, Any] = {
                "KeyConditionExpression": key_condition_expression,
                "ScanIndexForward": bool(scan_index_forward),
                "Limit": lim,
            }
            if index_name:
                kwargs["IndexName"] = index_name
            if filter_expression is not None:
                kwargs["FilterExpression"] = filter_expression
            # Important: only pass ExclusiveStartKey when present.
            if isinstance(lek, dict) and lek:
                kwargs["ExclusiveStartKey"] = lek
            return self._table.query(**kwargs)

        resp = ddb_call("Query", _op, table_name=self.table_name)
        items = resp.get("Items") or []
        out_lek = resp.get("LastEvaluatedKey")
        return Page(items=items, next_token=encode_next_token(out_lek))

    # --- transactions ---

    def transact_write(
        self,
        *,
        puts: Iterable[dict[str, Any]] = (),
        deletes: Iterable[dict[str, Any]] = (),
        updates: Iterable[dict[str, Any]] = (),
        retry_policy: RetryPolicy | None = None,
    ) -> dict[str, Any]:
        # Each put/delete/update entry should already be in DynamoDB client shape.
        items: list[dict[str, Any]] = []
        for p in puts:
            items.append({"Put": p})
        for d in deletes:
            items.append({"Delete": d})
        for u in updates:
            items.append({"Update": u})

        if not items:
            return {"ok": True}

        def _op():
            return self._client.transact_write_items(TransactItems=items)

        # transaction conflicts are mapped retryable by retry layer.
        return ddb_call(
            "TransactWriteItems",
            _op,
            table_name=self.table_name,
            retry_policy=retry_policy or RetryPolicy(max_attempts=8, base_delay_s=0.08, max_delay_s=2.0),
        )

    # Convenience builders for transact items (client shape)

    def tx_put(
        self,
        *,
        item: dict[str, Any],
        condition_expression: str | None = None,
        expression_attribute_names: dict[str, str] | None = None,
        expression_attribute_values: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        out: dict[str, Any] = {
            "TableName": self.table_name,
            "Item": _serialize_item(item),
        }
        if condition_expression:
            out["ConditionExpression"] = condition_expression
        if expression_attribute_names:
            out["ExpressionAttributeNames"] = expression_attribute_names
        if expression_attribute_values:
            out["ExpressionAttributeValues"] = _serialize_item(expression_attribute_values)
        return out

    def tx_delete(
        self,
        *,
        key: dict[str, Any],
        condition_expression: str | None = None,
        expression_attribute_names: dict[str, str] | None = None,
        expression_attribute_values: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        out: dict[str, Any] = {
            "TableName": self.table_name,
            "Key": _serialize_item(key),
        }
        if condition_expression:
            out["ConditionExpression"] = condition_expression
        if expression_attribute_names:
            out["ExpressionAttributeNames"] = expression_attribute_names
        if expression_attribute_values:
            out["ExpressionAttributeValues"] = _serialize_item(expression_attribute_values)
        return out

    def tx_update(
        self,
        *,
        key: dict[str, Any],
        update_expression: str,
        expression_attribute_names: dict[str, str] | None,
        expression_attribute_values: dict[str, Any],
        condition_expression: str | None = None,
    ) -> dict[str, Any]:
        out: dict[str, Any] = {
            "TableName": self.table_name,
            "Key": _serialize_item(key),
            "UpdateExpression": update_expression,
            "ExpressionAttributeValues": _serialize_item(expression_attribute_values),
        }
        if expression_attribute_names:
            out["ExpressionAttributeNames"] = expression_attribute_names
        if condition_expression:
            out["ConditionExpression"] = condition_expression
        return out


def get_main_table() -> DynamoTable:
    from ...settings import settings

    if not settings.ddb_table_name:
        raise DdbInternal(message="DDB_TABLE_NAME is not set", operation="Config")
    return DynamoTable(table_name=settings.ddb_table_name)


def get_table(table_name: str) -> DynamoTable:
    return DynamoTable(table_name=table_name)
