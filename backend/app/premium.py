"""Premium access helpers, including explicitly configured test accounts."""

import json

from app.config import settings


def premium_test_emails() -> set[str]:
    configured = settings().premium_test_emails
    try:
        values = json.loads(configured) if configured.lstrip().startswith('[') else configured.replace(';', ',').split(',')
    except json.JSONDecodeError:
        values = configured.replace(';', ',').split(',')
    if not isinstance(values, list):
        values = [values]
    return {email.strip().casefold() for email in values if isinstance(email, str) and email.strip()}


def has_premium_access(user) -> bool:
    return bool(user.is_premium or (user.email and user.email.casefold() in premium_test_emails()))