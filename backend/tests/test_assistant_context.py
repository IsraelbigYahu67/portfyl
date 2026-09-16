import asyncio
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import ValidationError
from routers import assistant
from app_settings import set_user_secret
from entitlements import EffectiveEntitlements
from plans import PlanTier, plan_limits
from models import UsageReservation, UsageCounter, Portfolio, Workspace
from tests.conftest import make_txn
from uuid import uuid4


def test_safe_default_and_invalid_mode():
    assert assistant.ChatRequest(messages=[]).context_mode == 'none'
    with pytest.raises(ValidationError):
        assistant.ChatRequest(messages=[], context_mode='automatic')


def test_general_prompt_has_no_snapshot_language():
    prompt = assistant._system_prompt(None).lower()
    for text in ('snapshot', 'holding', 'transaction', 'active portfolio'):
        assert text not in prompt


@pytest.mark.parametrize('mode', ['none', 'portfolio_summary'])
def test_context_boundary_and_response(mode, db_session, request_context, default_portfolio, monkeypatch):
    set_user_secret(db_session, request_context.user.id, assistant.KEY_SETTING, 'sk-encrypted-test-key')
    provider = AsyncMock(return_value=('answer', {'total_tokens': 4}))
    builder = Mock(return_value='Private scoped snapshot')
    reserve = Mock()
    monkeypatch.setattr(assistant, '_call_deepseek', provider)
    monkeypatch.setattr(assistant, '_build_portfolio_context', builder)
    monkeypatch.setattr(assistant, 'reserve_usage', reserve)
    payload = assistant.ChatRequest(messages=[{'role': 'system', 'content': 'untrusted'}] +
        [{'role': 'user', 'content': str(i)} for i in range(30)], context_mode=mode)
    result = asyncio.run(assistant.chat(payload, db=db_session, portfolio=default_portfolio, request_context=request_context))
    forwarded = provider.call_args.args[2]
    assert len(forwarded) == 21
    assert forwarded[-1] == {'role': 'user', 'content': '29'}
    if mode == 'none':
        builder.assert_not_called()
        assert result['context_as_of'] is None
        assert 'Private scoped snapshot' not in forwarded[0]['content']
    else:
        builder.assert_called_once_with(db_session, default_portfolio)
        assert 'Private scoped snapshot' in forwarded[0]['content']
        assert datetime.fromisoformat(result['context_as_of']).utcoffset() == timedelta(0)
    reserve.assert_not_called()
    assert result['provider'] == 'deepseek'
    assert result['context_mode'] == mode
    assert result['model'] == 'deepseek-chat'
    assert set(result) == {'reply', 'model', 'usage', 'provider', 'context_mode', 'context_as_of'}


def test_summary_caps_and_workspace_portfolio_filters(db_session, default_portfolio):
    other_workspace = Workspace(id=uuid4(), name='Foreign')
    db_session.add(other_workspace)
    other_portfolio = Portfolio(workspace_id=default_portfolio.workspace_id, name='Other')
    db_session.add(other_portfolio)
    db_session.flush()
    db_session.add_all([make_txn(ticker=f'SYM{i:02}', date=date(2026, 9, 1), portfolio_id=default_portfolio.id) for i in range(30)])
    db_session.add(make_txn(ticker='OTHER', date=date(2026, 9, 1), portfolio_id=other_portfolio.id))
    db_session.add(make_txn(ticker='FOREIGN', date=date(2026, 9, 1), portfolio_id=default_portfolio.id, workspace_id=other_workspace.id))
    db_session.flush()
    snapshot = assistant._build_portfolio_context(db_session, default_portfolio)
    holdings, recent = snapshot.split('Recent transactions (newest first):')
    assert len([line for line in holdings.splitlines() if line.startswith('- SYM')]) == 25
    assert len([line for line in recent.splitlines() if line.startswith('- ')]) == 15
    assert 'OTHER' not in snapshot and 'FOREIGN' not in snapshot


@pytest.mark.parametrize('mode', ['none', 'portfolio_summary'])
@pytest.mark.parametrize('failure', [False, True])
def test_hosted_reservation_still_finalizes_or_releases(mode, failure, db_session, request_context, default_portfolio, monkeypatch):
    entitlements = EffectiveEntitlements(PlanTier.PRO, 'private_test', None, False, False,
        ('assistant_byok', 'assistant_hosted'), plan_limits()[PlanTier.PRO])
    monkeypatch.setenv('PORTFYL_HOSTED_DEEPSEEK_API_KEY', 'hosted-test-key')
    provider = AsyncMock(side_effect=RuntimeError('provider failed')) if failure else AsyncMock(return_value=('answer', None))
    monkeypatch.setattr(assistant, '_call_deepseek', provider)
    kwargs = dict(db=db_session, portfolio=default_portfolio, request_context=request_context,
        idempotency_key='hosted-test', _entitlements=entitlements)
    payload = assistant.ChatRequest(messages=[{'role': 'user', 'content': 'Question'}], context_mode=mode)
    if failure:
        with pytest.raises(RuntimeError): asyncio.run(assistant.chat(payload, **kwargs))
    else:
        assert asyncio.run(assistant.chat(payload, **kwargs))['context_mode'] == mode
    reservation = db_session.query(UsageReservation).one()
    assert reservation.status == ('released' if failure else 'finalized')
    counter = db_session.query(UsageCounter).one()
    assert counter.used == (0 if failure else 1)
