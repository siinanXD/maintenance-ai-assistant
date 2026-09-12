"""Parameter-driven query cores behind the structured agent tools.

Each module exposes pure functions ``(user, **filters) -> QueryOutcome``. They
never parse chat text; the model (or the offline mock policy) supplies explicit
arguments. Visibility and permission rules are enforced inside every function.
"""
