from __future__ import annotations

from typing import Any, Iterable


ROLE_MEMBER = "Member"
ROLE_OPERATOR = "Operator"
ROLE_ADMIN = "Admin"


def normalize_roles(value: Any) -> list[str]:
    """
    Normalize roles to a canonical list of strings.
    Stored roles are TitleCase strings: Member/Operator/Admin.
    """
    roles_in: Iterable[Any]
    if isinstance(value, list):
        roles_in = value
    elif isinstance(value, tuple):
        roles_in = list(value)
    elif isinstance(value, str) and value.strip():
        roles_in = [value]
    else:
        roles_in = []

    out: list[str] = []
    for r in roles_in:
        s = str(r or "").strip()
        if not s:
            continue
        # Accept common variants.
        low = s.lower().replace("_", "").replace("-", "")
        if low in ("admin",):
            canon = ROLE_ADMIN
        elif low in ("operator", "ops"):
            canon = ROLE_OPERATOR
        elif low in ("member", "user", "basic"):
            canon = ROLE_MEMBER
        else:
            # Unknown roles allowed but normalized to TitleCase-ish.
            canon = s[:1].upper() + s[1:]
        if canon not in out:
            out.append(canon)

    if not out:
        out = [ROLE_MEMBER]
    return out


def has_role(roles: Any, want: str) -> bool:
    want2 = str(want or "").strip()
    if not want2:
        return False
    rr = normalize_roles(roles)
    return want2 in rr


def is_operator_or_admin(roles: Any) -> bool:
    rr = normalize_roles(roles)
    return ROLE_ADMIN in rr or ROLE_OPERATOR in rr


def is_admin(roles: Any) -> bool:
    rr = normalize_roles(roles)
    return ROLE_ADMIN in rr


