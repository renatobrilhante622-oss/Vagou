"""OTP lockout and single-use handlers with an isolated transactional fake session."""
import importlib.util
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import uuid

READY = bool(importlib.util.find_spec('sqlalchemy') and importlib.util.find_spec('email_validator'))


@unittest.skipUnless(READY, 'SQLAlchemy/email-validator unavailable; OTP handler checks not executed')
class VerificationHandlers(unittest.IsolatedAsyncioTestCase):
    async def test_failed_attempt_is_committed_and_never_verifies(self):
        from app.auth import verification_digest, verify_email
        from app.schemas import VerifyEmail
        from fastapi import HTTPException
        from pydantic import SecretStr
        cfg = SimpleNamespace(jwt_secret=SecretStr('verification-test-key-with-over-32-bytes'), verification_max_attempts=5)
        user = SimpleNamespace(id=uuid.uuid4(), email_verified=False)
        challenge = SimpleNamespace(version=uuid.uuid4(), expires_at=datetime.now(timezone.utc) + timedelta(minutes=10), attempts=0)
        db = SimpleNamespace(scalar=AsyncMock(return_value=user), get=AsyncMock(return_value=challenge), commit=AsyncMock())
        with patch('app.auth.settings', return_value=cfg):
            challenge.code_digest = verification_digest(user.id, challenge.version, '001234')
            with self.assertRaises(HTTPException) as result:
                await verify_email(VerifyEmail(email='candidate@example.com', code='999999'), db)
        self.assertEqual(result.exception.status_code, 400)
        self.assertEqual(challenge.attempts, 1)
        self.assertFalse(user.email_verified)
        db.commit.assert_awaited_once()

    async def test_success_consumes_challenge_and_pending_mail(self):
        from app.auth import verification_digest, verify_email
        from app.schemas import VerifyEmail
        from pydantic import SecretStr
        cfg = SimpleNamespace(jwt_secret=SecretStr('verification-test-key-with-over-32-bytes'), verification_max_attempts=5)
        user = SimpleNamespace(id=uuid.uuid4(), email_verified=False)
        challenge = SimpleNamespace(version=uuid.uuid4(), expires_at=datetime.now(timezone.utc) + timedelta(minutes=10), attempts=0)
        db = SimpleNamespace(scalar=AsyncMock(return_value=user), get=AsyncMock(return_value=challenge), commit=AsyncMock(), delete=AsyncMock(), execute=AsyncMock())
        with patch('app.auth.settings', return_value=cfg):
            challenge.code_digest = verification_digest(user.id, challenge.version, '001234')
            result = await verify_email(VerifyEmail(email='candidate@example.com', code='001234'), db)
        self.assertTrue(result['verified'])
        self.assertTrue(user.email_verified)
        db.delete.assert_awaited_once_with(challenge)
        db.execute.assert_awaited_once()
        db.commit.assert_awaited_once()
        from fastapi import HTTPException
        with self.assertRaises(HTTPException):
            await verify_email(VerifyEmail(email='candidate@example.com', code='001234'), db)

    async def test_expired_and_exhausted_codes_rejected_before_comparison(self):
        from app.auth import verify_email
        from app.schemas import VerifyEmail
        from fastapi import HTTPException
        for expires_at, attempts in [(datetime.now(timezone.utc) - timedelta(seconds=1), 0), (datetime.now(timezone.utc) + timedelta(minutes=10), 5)]:
            user = SimpleNamespace(id=uuid.uuid4(), email_verified=False)
            challenge = SimpleNamespace(expires_at=expires_at, attempts=attempts)
            db = SimpleNamespace(scalar=AsyncMock(return_value=user), get=AsyncMock(return_value=challenge))
            with patch('app.auth.settings', return_value=SimpleNamespace(verification_max_attempts=5)):
                with self.assertRaises(HTTPException):
                    await verify_email(VerifyEmail(email='candidate@example.com', code='001234'), db)
            self.assertFalse(user.email_verified)
