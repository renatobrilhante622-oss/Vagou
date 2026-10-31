"""Single server-side policy shared by API, workers and the account contract."""
from sqlalchemy import func, or_

from app.config import settings
from app.models import User


def test_emails() -> set[str]:
    cfg = settings()
    if cfg.environment not in ('development', 'test'):
        return set()
    return {email.strip().casefold() for email in cfg.premium_test_emails if email.strip()}


def can_automate(user: User) -> bool:
    return (user.role == 'candidate' and user.email_verified is True
            and (user.is_premium is True or user.email.casefold() in test_emails()))


def premium_filter():
    allowed = test_emails()
    paid = User.is_premium.is_(True)
    return or_(paid, func.lower(User.email).in_(allowed)) if allowed else paid


def entitlement_view(user: User) -> dict:
    test_access = user.email.casefold() in test_emails() and user.role == 'candidate'
    allowed = can_automate(user)
    reason = ('role_not_allowed' if user.role != 'candidate' else
              'email_verification_required' if not user.email_verified else
              'available' if allowed else 'premium_required')
    return {'plan': 'premium' if user.is_premium is True else 'test' if test_access else 'free',
            'can_automate': allowed, 'is_test_access': test_access, 'reason': reason}
