"""Delivery errors preserve saved registrations; OTP logging is explicit test-only."""
import io
import asyncio
import unittest
import uuid
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from app.verification_debug import log_verification_fallback


class DebugCodeTests(unittest.TestCase):
    def test_code_is_silent_by_default_and_in_production(self):
        for environment, enabled in [('production', False), ('production', True), ('development', False), ('test', False)]:
            output = io.StringIO()
            with patch('app.verification_debug.settings', return_value=SimpleNamespace(environment=environment, debug_verification_codes=enabled)), redirect_stdout(output):
                log_verification_fallback('001234')
            self.assertEqual(output.getvalue(), '')

    def test_explicit_development_and_test_debug_flush_code(self):
        for environment in ['development', 'test']:
            output = io.StringIO()
            with patch('app.verification_debug.settings', return_value=SimpleNamespace(environment=environment, debug_verification_codes=True)), redirect_stdout(output):
                log_verification_fallback('001234')
            self.assertEqual(output.getvalue(), 'DEBUG VERIFICATION CODE: 001234\n')


class DeliveryFailures(unittest.IsolatedAsyncioTestCase):
    async def test_slow_provider_does_not_hold_registration_open(self):
        from app.auth import attempt_verification_delivery
        async def delayed(**kwargs):
            await asyncio.sleep(1)
        with patch('app.auth.email_configured', return_value=True), patch('app.auth.process_email_outbox', side_effect=delayed), patch('app.auth.settings', return_value=SimpleNamespace(verification_delivery_timeout_seconds=0.01)), patch('app.auth.log_verification_fallback'):
            self.assertEqual(await attempt_verification_delivery(uuid.uuid4(), '001234'), 'retrying')

    async def test_failure_keeps_retry_status_and_requests_debug_fallback(self):
        from app.auth import attempt_verification_delivery
        for result, error in [({'sent': 0}, None), (None, OSError('private provider response'))]:
            task = AsyncMock(return_value=result, side_effect=error)
            with patch('app.auth.email_configured', return_value=True), patch('app.auth.process_email_outbox', task), patch('app.auth.log_verification_fallback') as fallback:
                self.assertEqual(await attempt_verification_delivery(uuid.uuid4(), '001234'), 'retrying')
                fallback.assert_called_once_with('001234')

    async def test_unconfigured_transport_keeps_pending_account(self):
        from app.auth import attempt_verification_delivery
        with patch('app.auth.email_configured', return_value=False), patch('app.auth.process_email_outbox', AsyncMock()) as delivery, patch('app.auth.log_verification_fallback') as fallback:
            self.assertEqual(await attempt_verification_delivery(uuid.uuid4(), '001234'), 'configuration_required')
            delivery.assert_not_awaited()
            fallback.assert_called_once_with('001234')

    async def test_accepted_message_never_prints_code(self):
        from app.auth import attempt_verification_delivery
        with patch('app.auth.email_configured', return_value=True), patch('app.auth.process_email_outbox', AsyncMock(return_value={'sent': 1})), patch('app.auth.log_verification_fallback') as fallback:
            self.assertEqual(await attempt_verification_delivery(uuid.uuid4(), '001234'), 'sent')
            fallback.assert_not_called()

    async def test_registration_commits_before_delivery_failure(self):
        from app.auth import register
        from app.schemas import Register
        user = SimpleNamespace(id=uuid.uuid4())
        db = SimpleNamespace(add=Mock(), flush=AsyncMock(), commit=AsyncMock(), rollback=AsyncMock())
        async def deliver(*args):
            db.commit.assert_awaited_once()
            return 'retrying'
        with patch('app.auth.User', return_value=user), patch('app.auth.hash_password', return_value='test-hash'), patch('app.auth.queue_verification', AsyncMock(return_value='001234')), patch('app.auth.account_response', return_value={'email_verified': False}), patch('app.auth.attempt_verification_delivery', side_effect=deliver), patch('app.auth.settings', return_value=SimpleNamespace(privacy_version='2026-01')):
            result = await register(Register(email='candidate@example.com', password='Long-test-password!', name='Candidate', role='candidate', privacy_version='2026-01', consent=True), db)
        self.assertEqual(result['delivery_status'], 'retrying')
        self.assertFalse(result['email_verified'])
        db.rollback.assert_not_awaited()
