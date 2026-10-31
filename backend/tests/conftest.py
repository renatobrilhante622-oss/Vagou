"""Isolated defaults for unit tests; integration runs supply their own settings."""
import os
import secrets
from cryptography.fernet import Fernet

# Tests never discover a developer's private SMTP file or contact Gmail.
os.environ.setdefault('VAGOU_ENV_FILE', '/dev/null')
os.environ['ENABLE_PUBLIC_COLLECTORS'] = 'false'

if not os.environ.get('VAGOU_TEST_URL'):
    os.environ.setdefault('JWT_SECRET', secrets.token_urlsafe(48))
    os.environ.setdefault('DATA_KEY', Fernet.generate_key().decode())
    # Override .env discovery: unit tests must not select a developer database.
    os.environ.setdefault('DATABASE_URL', 'postgresql+asyncpg://unit:unit@localhost/vagou_unit')
