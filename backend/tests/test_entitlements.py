from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app import entitlements


def account(**overrides):
    return SimpleNamespace(id=uuid4(), role='candidate', email_verified=True,
        is_premium=False, email='tester@example.com', automation_enabled=True,
        resume_key='private-pdf', preferences={'titles': ['Python'], 'modalities': ['remote']}, **overrides)


@pytest.mark.parametrize('environment', ['production', 'development', 'test'])
def test_test_access_is_explicit_and_never_active_in_production(environment):
    cfg = SimpleNamespace(environment=environment, premium_test_emails=[' TESTER@example.com '])
    with patch('app.entitlements.settings', return_value=cfg):
        user = account()
        assert entitlements.can_automate(user) == (environment != 'production')
        assert user.is_premium is False
        user.email_verified = False
        assert not entitlements.can_automate(user)


def test_subscribers_and_free_accounts_share_one_strict_policy():
    cfg = SimpleNamespace(environment='production', premium_test_emails=[])
    with patch('app.entitlements.settings', return_value=cfg):
        user = account()
        assert not entitlements.entitlement_view(user)['can_automate']
        user.is_premium = True
        assert entitlements.entitlement_view(user)['can_automate']
        user.role = 'recruiter'
        assert not entitlements.can_automate(user)
        user.role = 'candidate'
        user.is_premium = 'false'
        assert not entitlements.can_automate(user)


@pytest.mark.parametrize('acquired', [True, False])
def test_immediate_dispatch_is_scoped_and_deduplicated(acquired):
    import asyncio
    from app.automation import enqueue_now
    user = account()
    user.is_premium = True
    redis = SimpleNamespace(set=AsyncMock(return_value=acquired), eval=AsyncMock())
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(redis=redis)))
    with patch('app.worker.run_automation.apply_async') as enqueue:
        result = asyncio.run(enqueue_now(request, user))
    assert result['status'] == 'queued'
    assert result['deduplicated'] == (not acquired)
    if acquired:
        assert enqueue.call_args.kwargs['args'] == [str(user.id)]
        assert enqueue.call_args.kwargs['kwargs'] == {'force': True}
    else:
        enqueue.assert_not_called()


def test_broker_failure_returns_retryable_error_and_releases_reservation():
    import asyncio
    from app.automation import enqueue_now
    user = account()
    user.is_premium = True
    redis = SimpleNamespace(set=AsyncMock(return_value=True), eval=AsyncMock())
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(redis=redis)))
    with patch('app.worker.run_automation.apply_async', side_effect=ConnectionError('broker')):
        with pytest.raises(HTTPException) as error:
            asyncio.run(enqueue_now(request, user))
    assert error.value.status_code == 503
    redis.eval.assert_awaited_once()


def test_preferences_salary_interval_and_optional_maximum():
    from app.schemas import Preferences
    assert Preferences(min_salary=5000).max_salary is None
    assert Preferences(min_salary=5000, max_salary=7000).max_salary == 7000
    with pytest.raises(ValueError):
        Preferences(min_salary=7000, max_salary=5000)
