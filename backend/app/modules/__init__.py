"""
Modular monolith package.

New bounded-context modules live under `backend/app/modules/*`.
Routers should call application services within modules rather than directly
invoking repositories or infrastructure adapters.
"""


