"""Server-owned administrative entitlements; public signup never assigns staff roles."""

OWNER_EMAIL = "rbrilhante001@gmail.com"


def is_owner(user):
    return str(getattr(user, "email", "")).casefold() == OWNER_EMAIL


def is_admin(user):
    return getattr(user, "role", "") in {"super_admin", "moderator"}


def ensure_owner(user):
    if is_owner(user):
        user.role = "super_admin"
        user.is_premium = True
        user.is_active = True
