"""Focused mocked regressions for chatbot diagnostic logging and HTTP502 error paths."""
import logging
import pytest
from tests.test_chatbot_provider import sdk, ask, assert_error, APIError, response, part


@pytest.mark.parametrize('code', [500, 502, 503])
def test_diagnostic_logging_on_upstream_server_errors(sdk, code, caplog):
    caplog.set_level(logging.INFO, logger='trustmebro.chatbot')
    sdk.error = APIError(code)
    result = ask(sdk)
    assert_error(result, 502, 'provider_unavailable')

    assert 'chatbot_diagnostic' in caplog.text
    assert 'stage=transport' in caplog.text
    assert 'exc=APIError' in caplog.text
    assert f'upstream_status={code}' in caplog.text
    assert 'code=provider_unavailable' in caplog.text
    assert 'req_id=' in caplog.text
    assert 'SECRET_PROVIDER_SENTINEL' not in caplog.text


def test_diagnostic_logging_on_upstream_rate_limit_429(sdk, caplog):
    caplog.set_level(logging.INFO, logger='trustmebro.chatbot')
    sdk.error = APIError(429)
    result = ask(sdk)
    assert_error(result, 502, 'provider_unavailable')
    assert result.headers['retry-after'] == '60'

    assert 'chatbot_diagnostic' in caplog.text
    assert 'stage=transport' in caplog.text
    assert 'exc=APIError' in caplog.text
    assert 'upstream_status=429' in caplog.text
    assert 'code=provider_unavailable' in caplog.text
    assert 'SECRET_PROVIDER_SENTINEL' not in caplog.text


def test_diagnostic_logging_on_transport_network_failure(sdk, caplog):
    caplog.set_level(logging.INFO, logger='trustmebro.chatbot')

    class MockConnectError(Exception):
        pass

    sdk.error = MockConnectError('SENSITIVE_SOCKET_TRACE')
    result = ask(sdk)
    assert_error(result, 502, 'provider_unavailable')

    assert 'chatbot_diagnostic' in caplog.text
    assert 'stage=transport' in caplog.text
    assert 'exc=MockConnectError' in caplog.text
    assert 'upstream_status=None' in caplog.text
    assert 'code=provider_unavailable' in caplog.text
    assert 'SENSITIVE_SOCKET_TRACE' not in caplog.text


def test_diagnostic_logging_on_parse_stage_invalid_response(sdk, caplog):
    caplog.set_level(logging.INFO, logger='trustmebro.chatbot')
    sdk.result = response('text', finish='OTHER')
    result = ask(sdk)
    assert_error(result, 502, 'provider_invalid_response')

    assert 'chatbot_diagnostic' in caplog.text
    assert 'stage=parse' in caplog.text
    assert 'code=provider_invalid_response' in caplog.text
    assert 'upstream_status=None' in caplog.text


def test_diagnostic_logging_on_successful_answer(sdk, caplog):
    caplog.set_level(logging.INFO, logger='trustmebro.chatbot')
    result = ask(sdk, message='Merkle proof là gì?')
    assert result.status_code == 200
    assert result.json()['code'] == 'answered'

    assert 'chatbot_diagnostic' in caplog.text
    assert 'stage=complete' in caplog.text
    assert 'code=answered' in caplog.text
    assert 'req_id=' in caplog.text
    assert 'elapsed=' in caplog.text
    assert 'Merkle proof là gì?' not in caplog.text


def test_diagnostic_logging_never_exposes_keys_or_messages(sdk, caplog):
    caplog.set_level(logging.INFO, logger='trustmebro.chatbot')
    secret_msg = 'PRIVATE_KEY_SECRET_PROMPT_QUERY'
    sdk.error = APIError(500)
    result = ask(sdk, message=secret_msg)
    assert result.status_code == 502

    assert secret_msg not in caplog.text
    assert 'FAKE_SDK_TEST_KEY' not in caplog.text
    assert 'SECRET_PROVIDER_SENTINEL' not in caplog.text


def test_contextvar_tokens_reset_on_success_and_failure(sdk):
    from api.chatbot_api import _current_req_id, _current_req_stage, _current_req_start

    # Initial state
    assert _current_req_id.get() is None
    assert _current_req_start.get() is None
    assert _current_req_stage.get() == 'init'

    # Success case
    res_ok = ask(sdk, message='What is blockchain?')
    assert res_ok.status_code == 200
    assert _current_req_id.get() is None
    assert _current_req_start.get() is None
    assert _current_req_stage.get() == 'init'

    # Error case
    sdk.error = APIError(503)
    res_err = ask(sdk)
    assert res_err.status_code == 502
    assert _current_req_id.get() is None
    assert _current_req_start.get() is None
    assert _current_req_stage.get() == 'init'


def test_logging_failure_does_not_mask_original_error(sdk, monkeypatch):
    from api.chatbot_api import logger

    def mock_log_fail(*args, **kwargs):
        raise IOError("Disk buffer full")

    monkeypatch.setattr(logger, 'warning', mock_log_fail)
    monkeypatch.setattr(logger, 'info', mock_log_fail)

    sdk.error = APIError(502)
    result = ask(sdk)
    # Logging failure must not mask the 502 provider_unavailable response
    assert_error(result, 502, 'provider_unavailable')


