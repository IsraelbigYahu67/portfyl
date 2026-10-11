from datetime import date, datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
from pydantic import ValidationError
from routers import assistant
from app_settings import set_user_secret
from entitlements import EffectiveEntitlements
from plans import PlanTier, plan_limits
from models import BrokerConnection, UsageReservation, UsageCounter, Portfolio, Workspace
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
    provider = Mock(return_value=('answer', {'total_tokens': 4}))
    builder = Mock(return_value='Private scoped snapshot')
    reserve = Mock()
    monkeypatch.setattr(assistant, '_call_deepseek', provider)
    monkeypatch.setattr(assistant, '_build_portfolio_context', builder)
    monkeypatch.setattr(assistant, 'reserve_usage', reserve)
    payload = assistant.ChatRequest(messages=[{'role': 'system', 'content': 'untrusted'}] +
        [{'role': 'user', 'content': str(i)} for i in range(30)], context_mode=mode)
    result = assistant.chat(payload, db=db_session, portfolio=default_portfolio, request_context=request_context)
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


def test_recent_transactions_use_execution_time_within_same_day(
    db_session, default_portfolio
):
    afternoon_buy = make_txn(
        ticker='AAPL', type='buy', shares=1, price=100,
        date=date(2026, 9, 1), portfolio_id=default_portfolio.id,
    )
    afternoon_buy.executed_at = datetime(2026, 9, 1, 15, 0, tzinfo=timezone.utc)
    morning_sell = make_txn(
        ticker='AAPL', type='sell', shares=1, price=110,
        date=date(2026, 9, 1), portfolio_id=default_portfolio.id,
    )
    morning_sell.executed_at = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)
    db_session.add_all([afternoon_buy, morning_sell])
    db_session.commit()

    recent = assistant._build_portfolio_context(
        db_session, default_portfolio,
    ).split('Recent transactions (newest first):', 1)[1]

    assert recent.index(' BUY ') < recent.index(' SELL ')


def test_t212_context_marks_broker_history_incomplete_even_after_pages_are_downloaded(
    db_session, default_portfolio
):
    db_session.add(BrokerConnection(
        workspace_id=default_portfolio.workspace_id,
        portfolio_id=default_portfolio.id,
        broker='trading212', api_key='test-key', api_secret='',
    ))
    db_session.add(make_txn(ticker='AAPL', date=date(2026, 9, 1), portfolio_id=default_portfolio.id))
    db_session.commit()

    context = assistant._build_portfolio_context(db_session, default_portfolio)
    prompt = assistant._system_prompt(context)

    assert 'history_complete=false' in context
    assert 'broker history may be missing from the transaction ledger' in context.lower()
    assert 'qualify historical claims' in prompt.lower()


def test_t212_context_keeps_history_warning_after_disconnect(db_session, default_portfolio):
    default_portfolio.t212_account_fingerprint = 'a' * 64
    db_session.add(make_txn(ticker='AAPL', date=date(2026, 9, 1), portfolio_id=default_portfolio.id))
    db_session.commit()

    context = assistant._build_portfolio_context(db_session, default_portfolio)

    assert 'history_complete=false' in context


def test_assistant_uses_paid_dividend_cash_amount_when_available(db_session, default_portfolio):
    dividend = make_txn(
        ticker='AAPL', type='dividend', shares=10, price=1.0,
        date=date(2026, 9, 1), portfolio_id=default_portfolio.id,
    )
    dividend.cash_amount = 8.5
    dividend.cash_currency = 'USD'
    db_session.add(dividend)
    db_session.commit()

    context = assistant._build_portfolio_context(db_session, default_portfolio)

    assert 'Recorded dividend income (approx): 8.50 USD' in context
    assert '10.00 USD' not in context.split('Recorded dividend income (approx):')[1].splitlines()[0]


@pytest.mark.parametrize('mode', ['none', 'portfolio_summary'])
@pytest.mark.parametrize('failure', [False, True])
def test_hosted_reservation_still_finalizes_or_releases(mode, failure, db_session, request_context, default_portfolio, monkeypatch):
    entitlements = EffectiveEntitlements(PlanTier.PRO, 'private_test', None, False, False,
        ('assistant_byok', 'assistant_hosted'), plan_limits()[PlanTier.PRO])
    monkeypatch.setenv('PORTFYL_HOSTED_DEEPSEEK_API_KEY', 'hosted-test-key')
    provider = Mock(side_effect=RuntimeError('provider failed')) if failure else Mock(return_value=('answer', None))
    monkeypatch.setattr(assistant, '_call_deepseek', provider)
    kwargs = dict(db=db_session, portfolio=default_portfolio, request_context=request_context,
        idempotency_key='hosted-test', _entitlements=entitlements)
    payload = assistant.ChatRequest(messages=[{'role': 'user', 'content': 'Question'}], context_mode=mode)
    if failure:
        with pytest.raises(RuntimeError): assistant.chat(payload, **kwargs)
    else:
        assert assistant.chat(payload, **kwargs)['context_mode'] == mode
    reservation = db_session.query(UsageReservation).one()
    assert reservation.status == ('released' if failure else 'finalized')
    counter = db_session.query(UsageCounter).one()
    assert counter.used == (0 if failure else 1)
