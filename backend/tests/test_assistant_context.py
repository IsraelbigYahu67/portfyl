import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import ValidationError
from routers import assistant
from app_settings import set_user_secret


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
