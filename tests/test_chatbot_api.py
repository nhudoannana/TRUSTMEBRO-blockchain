"""Chat contract tests use in-process ASGI and fake providers; never Gemini."""
import asyncio
import importlib
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from api import session_store
from api.session_store import COOKIE_NAME, SessionRegistry
from api.wallet_api import app


@pytest.fixture
def chat(monkeypatch):
    now = [0.0]
    registry = SessionRegistry(clock=lambda: now[0], idle_seconds=100000, capacity=8)
    monkeypatch.setattr(session_store, 'registry', registry)
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    monkeypatch.delenv('GOOGLE_API_KEY', raising=False)
    monkeypatch.setenv('CHATBOT_ENABLED', '0')
    calls = []

    async def fake(message, history):
        calls.append((message, history))
        return {'code': 'answered', 'answer': 'Câu trả lời giả để kiểm tra.', 'lab_links': []}

    monkeypatch.setattr(app.state, 'chatbot_provider', fake, raising=False)
    try:
        api = importlib.import_module('api.chatbot_api')
    except ModuleNotFoundError:
        api = None  # Baseline RED still exercises the absent HTTP contract.
    if api is not None:
        monkeypatch.setattr(app.state, 'chatbot_budget', api.ChatbotBudget(clock=lambda: now[0]))
    with TestClient(app) as client:
        generation = client.get('/api/session/bootstrap').json()['context_generation']
        ctx = registry.entries[client.cookies.get(COOKIE_NAME)]
        yield SimpleNamespace(client=client, generation=generation, ctx=ctx, calls=calls,
                              registry=registry, now=now, api=api, monkeypatch=monkeypatch)
    registry.shutdown()


def body(chat, **updates):
    return {'context_generation': chat.generation, 'message': 'Merkle proof chứng minh gì?',
            'history': [], **updates}


def post(chat, **updates):
    return chat.client.post('/api/chatbot', content=json.dumps(body(chat, **updates)).encode(),
                            headers={'content-type': 'application/json'})


def assert_error(response, status, code):
    assert response.status_code == status, response.text
    assert response.json()['detail']['code'] == code


def test_status_is_configuration_only_and_does_not_seed_domain(chat):
    response = chat.client.get('/api/chatbot/status')
    assert response.status_code == 200
    data = response.json()
    assert data['configured'] and data['code'] == 'configured'
    assert data['provider_verified'] is False
    assert data['context_generation'] == chat.generation
    assert data['limits'] == {'message_bytes': 2048, 'history_messages': 6,
                              'history_bytes': 12288, 'answer_bytes': 4096}
    assert not chat.calls and chat.ctx.network is None
    assert not chat.ctx.wallets._store and not chat.ctx.signed_credentials


def test_success_preserves_text_history_and_never_passes_session_to_provider(chat):
    history = [{'role': 'user', 'content': 'Hash?'}, {'role': 'assistant', 'content': 'Cam kết.'}]
    response = post(chat, message='  Câu hỏi\n', history=history)
    assert response.status_code == 200
    data = response.json()
    assert data['code'] == 'answered' and data['is_ai'] is True
    assert data['context_generation'] == chat.generation and not data['truncated']
    assert chat.calls == [('  Câu hỏi\n', history)]
    assert response.headers['cache-control'] == 'no-store'
    assert response.headers['x-simulation-generation'] == chat.generation


@pytest.mark.parametrize('updates', [
    {'message': ''}, {'message': ' \n'}, {'message': 1}, {'message': None},
    {'message': 'é' * 1025}, {'message': '\ud800'}, {'history': None},
    {'history': [{'role': 'user', 'content': 'x'}]},
    {'history': [{'role': 'system', 'content': 'x'}, {'role': 'assistant', 'content': 'y'}]},
    {'history': [{'role': 'assistant', 'content': 'x'}, {'role': 'user', 'content': 'y'}]},
    {'history': [{'role': 'user', 'content': 'x', 'tools': []}, {'role': 'assistant', 'content': 'y'}]},
    {'history': [{'role': 'user', 'content': 'x' * 2049}, {'role': 'assistant', 'content': 'y'}]},
    {'history': [{'role': 'user', 'content': 'x'}, {'role': 'assistant', 'content': 'y' * 4097}]},
    {'history': [{'role': 'user', 'content': 'x'}, {'role': 'assistant', 'content': ' '}]},
    {'history': [{'role': 'user', 'content': 'x'}, {'role': 'assistant', 'content': 'y'}] * 4},
    {'history': [{'role': 'user', 'content': 'x' * 2048},
                 {'role': 'assistant', 'content': 'y' * 4096}] * 3},
    {'context_generation': ''}, {'context_generation': 'x' * 129},
    {'context_generation': 'bad space'}, {'context_generation': 42}, {'wallet': 'secret'},
])
def test_invalid_input_rejects_before_provider_without_echo(chat, updates):
    response = post(chat, **updates)
    assert_error(response, 422, 'invalid_input')
    assert set(response.json()['detail']) == {'code', 'message'}
    assert not chat.calls


@pytest.mark.parametrize('message', [
    '-----BEGIN RSA PRIVATE KEY-----\nsecret',
    'AIza' + 'a' * 20, 'a' * 64, 'z' * 128,
    '{"private_key":"SECRET_SENTINEL"}', '{"private_key_pem":"SECRET_SENTINEL"}',
    '{"wallets":[]}', '{"transactions":[]}', '{"mempool":[]}',
    '{"credential_id":"SECRET_SENTINEL"}', '{"key_handle":"SECRET_SENTINEL"}',
])
def test_sensitive_message_rejected_without_echo_or_provider(chat, message, caplog):
    response = post(chat, message=message)
    assert_error(response, 422, 'sensitive_input')
    assert 'SECRET_SENTINEL' not in response.text + caplog.text
    assert not chat.calls


def test_sensitive_history_rejected_and_theory_keyword_allowed(chat):
    response = post(chat, history=[{'role': 'user', 'content': 'Private key là gì?'},
                                  {'role': 'assistant', 'content': '{"wallets":[]}'}])
    assert_error(response, 422, 'sensitive_input')
    assert post(chat, message='Private key là gì?').status_code == 200


def test_exact_utf8_and_history_bounds_accepted(chat):
    # Spaces interrupt blob filters: byte limits must be independent of them.
    assert post(chat, message='é ' * 682 + 'é').status_code == 200  # exactly 2048 bytes
    history = [{'role': 'user', 'content': 'x ' * 1024},
               {'role': 'assistant', 'content': 'y ' * 1024}] * 3
    assert post(chat, history=history).status_code == 200  # exactly 12288 bytes
    assert len(chat.calls) == 2


@pytest.mark.parametrize('content,status,code', [
    (b'{"message":', 400, 'malformed_json'),
    (b'\xff', 400, 'malformed_json'),
    (b'{"message":"x","message":"y"}', 400, 'malformed_json'),
    (b'[' * 1200 + b']' * 1200, 422, 'invalid_input'),
    (b'x' * 32769, 413, 'body_too_large'),
], ids=['broken-json', 'invalid-utf8', 'duplicate-key', 'deep-json', 'oversize'])
def test_raw_body_failures_safe_and_no_provider(chat, content, status, code):
    response = chat.client.post('/api/chatbot', content=content,
                                headers={'content-type': 'application/json'})
    assert_error(response, status, code)
    assert not chat.calls


def test_actual_stream_bound_despite_small_content_length_and_valid_exact_body(chat):
    raw = json.dumps(body(chat)).encode()
    exact = raw + b' ' * (32768 - len(raw))
    response = chat.client.post('/api/chatbot', content=iter([exact[:16000], exact[16000:]]),
                               headers={'content-type': 'application/json'})
    assert response.status_code == 200
    response = chat.client.post('/api/chatbot', content=iter([b' ' * 16000, b' ' * 16769]),
                               headers={'content-type': 'application/json', 'content-length': '1'})
    assert_error(response, 413, 'body_too_large')
    assert len(chat.calls) == 1


@pytest.mark.parametrize('headers,status,code', [
    ({'content-type': 'text/plain'}, 415, 'unsupported_media_type'),
    ({'content-type': 'application/json', 'content-encoding': 'gzip'}, 415, 'unsupported_media_type'),
    ({'content-type': 'application/json', 'origin': 'null'}, 403, 'origin_rejected'),
    ({'content-type': 'application/json', 'origin': 'http://evil.invalid'}, 403, 'origin_rejected'),
    ({'content-type': 'application/json', 'content-length': 'no'}, 400, 'malformed_json'),
])
def test_transport_boundaries(chat, headers, status, code):
    assert_error(chat.client.post('/api/chatbot', content=json.dumps(body(chat)).encode(),
                                  headers=headers), status, code)
    assert not chat.calls


def test_same_origin_allowed_and_stale_generation_no_call(chat):
    assert post(chat).status_code == 200
    response = chat.client.post('/api/chatbot', json=body(chat),
                                headers={'origin': 'http://testserver'})
    assert response.status_code == 200
    assert_error(post(chat, context_generation='old-generation'), 409, 'session_changed')
    assert len(chat.calls) == 2


def test_production_disabled_and_missing_dependency_keep_existing_routes(chat):
    chat.monkeypatch.setattr(app.state, 'chatbot_provider', None)
    response = chat.client.get('/api/chatbot/status')
    assert response.status_code == 200 and response.json()['code'] == 'disabled'
    assert_error(post(chat), 503, 'chat_disabled')
    chat.monkeypatch.setenv('CHATBOT_ENABLED', '1')
    chat.monkeypatch.setattr(chat.api, '_sdk_available', lambda: False)
    assert chat.client.get('/api/chatbot/status').json()['code'] == 'sdk_missing'
    assert_error(post(chat), 503, 'sdk_unavailable')
    for path in ['/api/health', '/ui/labs.html', '/ui/quiz.html']:
        assert chat.client.get(path).status_code == 200
    assert chat.client.post('/api/labs/merkle', json={'leaves': ['A', 'B']}).status_code == 200
    assert not chat.calls


def test_missing_key_and_bad_config_are_truthful(chat):
    chat.monkeypatch.setattr(app.state, 'chatbot_provider', None)
    chat.monkeypatch.setenv('CHATBOT_ENABLED', '1')
    chat.monkeypatch.setattr(chat.api, '_sdk_available', lambda: True)
    assert chat.client.get('/api/chatbot/status').json()['code'] == 'key_missing'
    assert_error(post(chat), 503, 'key_unavailable')
    chat.monkeypatch.setenv('CHATBOT_ENABLED', 'unexpected')
    assert chat.client.get('/api/chatbot/status').json()['code'] == 'config_invalid'
    assert_error(post(chat), 503, 'provider_configuration')


def test_session_rate_windows_and_no_refund_on_failed_attempt(chat):
    async def failing(*args):
        chat.calls.append(args)
        raise RuntimeError('SECRET_SENTINEL')
    chat.monkeypatch.setattr(app.state, 'chatbot_provider', failing)
    for _ in range(6):
        response = post(chat)
        assert_error(response, 502, 'provider_unavailable')
        assert 'SECRET_SENTINEL' not in response.text
    denied = post(chat)
    assert_error(denied, 429, 'chat_rate_limited')
    assert denied.headers['retry-after'] == '60'
    chat.now[0] = 60
    assert_error(post(chat), 502, 'provider_unavailable')
    assert len(chat.calls) == 7


def test_hourly_session_limit_survives_journey_reset(chat):
    for minute in range(5):
        chat.now[0] = minute * 60
        for _ in range(6):
            assert post(chat).status_code == 200
    # Reset lab state cannot reset spending or concurrency.
    assert chat.client.post('/api/session/reset').status_code == 200
    chat.generation = chat.ctx.generation
    chat.now[0] = 300
    assert_error(post(chat), 429, 'chat_rate_limited')
    chat.now[0] = 3600
    assert post(chat).status_code == 200


def test_process_hour_day_limits_cannot_be_bypassed_by_new_cookie(chat):
    budget = app.state.chatbot_budget
    budget.attempts.extend([0.0] * 120)
    with peer() as other:
        generation = other.get('/api/session/bootstrap').json()['context_generation']
        assert_error(other.post('/api/chatbot', json=body(chat, context_generation=generation)),
                     429, 'chat_budget_exhausted')
    chat.now[0] = 3600
    assert post(chat).status_code == 200
    budget.attempts.clear()
    budget.attempts.extend([0.0] * 250)
    assert_error(post(chat), 429, 'chat_budget_exhausted')
    chat.now[0] = 86400
    assert post(chat).status_code == 200


def test_busy_and_global_capacity_then_actual_release(chat):
    entered = threading.Event()
    release = threading.Event()

    async def delayed(*args):
        entered.set()
        while not release.is_set():
            await asyncio.sleep(.001)
        return {'code': 'answered', 'answer': 'fake'}

    chat.monkeypatch.setattr(app.state, 'chatbot_provider', delayed)
    with peer() as other, peer() as third, ThreadPoolExecutor(2) as pool:
        gb = other.get('/api/session/bootstrap').json()['context_generation']
        gc = third.get('/api/session/bootstrap').json()['context_generation']
        first = pool.submit(post, chat)
        try:
            assert entered.wait(3)
            assert_error(post(chat), 409, 'chat_busy')
            entered.clear()
            second = pool.submit(other.post, '/api/chatbot', json=body(chat, context_generation=gb))
            assert entered.wait(3)
            assert_error(third.post('/api/chatbot', json=body(chat, context_generation=gc)),
                         503, 'chat_capacity')
            assert app.state.chatbot_budget.inflight == 2
        finally:
            release.set()
        assert first.result(3).status_code == second.result(3).status_code == 200
    assert app.state.chatbot_budget.inflight == 0 and not chat.ctx.chat_inflight
    assert post(chat).status_code == 200


def test_reset_during_provider_rejects_old_reply_and_preserves_admission(chat):
    entered, release = threading.Event(), threading.Event()

    async def delayed(*args):
        entered.set()
        while not release.is_set():
            await asyncio.sleep(.001)
        return {'code': 'answered', 'answer': 'OLD_REPLY'}

    chat.monkeypatch.setattr(app.state, 'chatbot_provider', delayed)
    with ThreadPoolExecutor(1) as pool:
        first = pool.submit(post, chat)
        try:
            assert entered.wait(3)
            assert chat.client.post('/api/session/reset').status_code == 200
            assert chat.ctx.chat_inflight  # Reset does not prematurely free provider capacity.
        finally:
            release.set()
        response = first.result(3)
    assert_error(response, 409, 'session_changed')
    assert 'OLD_REPLY' not in response.text
    chat.generation = chat.ctx.generation
    assert post(chat).status_code == 200
    assert len(chat.ctx.chat_attempts) == 2


def test_expiry_new_session_rejects_old_generation(chat):
    identifier = chat.client.cookies.get(COOKIE_NAME)
    chat.registry.idle_seconds = 10
    chat.now[0] = 10
    chat.registry.cleanup()
    assert identifier not in chat.registry.entries
    assert_error(post(chat), 409, 'session_changed')
    assert not chat.calls


def test_provider_timeout_and_cancel_release_real_operation(chat):
    chat.monkeypatch.setattr(chat.api, 'REQUEST_TIMEOUT_SECONDS', .02)
    cancelled = threading.Event()

    async def never(*args):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    chat.monkeypatch.setattr(app.state, 'chatbot_provider', never)
    assert_error(post(chat), 504, 'provider_timeout')
    assert cancelled.is_set()
    assert app.state.chatbot_budget.inflight == 0 and not chat.ctx.chat_inflight
    assert len(chat.ctx.chat_attempts) == 1


@pytest.mark.parametrize('result,status,code', [
    ({'code': 'answered', 'answer': ''}, 502, 'provider_invalid_response'),
    ({'code': 'answered', 'answer': None}, 502, 'provider_invalid_response'),
    ({'code': 'bad', 'answer': 'fake'}, 502, 'provider_invalid_response'),
    ({'code': 'blocked'}, 200, 'blocked'),
])
def test_provider_result_is_not_http200_success_automatically(chat, result, status, code):
    async def fake(*args):
        return result
    chat.monkeypatch.setattr(app.state, 'chatbot_provider', fake)
    response = post(chat)
    if status == 200:
        assert response.json()['code'] == code and response.json()['answer'] is None
    else:
        assert_error(response, status, code)


def test_full_output_is_utf8_bounded_and_provider_urls_never_trusted(chat):
    async def fake(*args):
        return {'code': 'answered', 'answer': 'é' * 3000,
                'lab_links': [{'id': 'x', 'href': 'javascript:alert(1)'}]}
    chat.monkeypatch.setattr(app.state, 'chatbot_provider', fake)
    response = post(chat)
    assert response.status_code == 200
    data = response.json()
    assert data['truncated'] and len(data['answer'].encode()) == 4096
    assert data['lab_links'] == [{'id': 'merkle', 'label': 'Cây Merkle', 'href': '/ui/labs.html#merkle'}]


@contextmanager
def peer():
    client = TestClient(app)  # Outer fixture owns the single shared app lifespan.
    try:
        yield client
    finally:
        client.close()


def test_slow_body_read_has_request_deadline_without_admission(chat):
    from starlette.requests import Request
    from api.session_store import bind_session
    chat.monkeypatch.setattr(chat.api, 'REQUEST_TIMEOUT_SECONDS', .02)

    async def run():
        async def receive():
            await asyncio.Event().wait()
        scope = {'type': 'http', 'method': 'POST', 'path': '/api/chatbot',
                 'scheme': 'http', 'server': ('testserver', 80), 'headers':
                 [(b'content-type', b'application/json')], 'app': app}
        with bind_session(chat.ctx):
            try:
                response = await asyncio.wait_for(chat.api.chatbot_post(Request(scope, receive)), .25)
            except TimeoutError:
                pytest.fail('Body parsing did not enforce the request deadline')
        assert response.status_code == 504
    asyncio.run(run())
    assert not chat.calls and not chat.ctx.chat_attempts
    assert app.state.chatbot_budget.inflight == 0


def test_cancellation_cleanup_keeps_slot_until_operation_ends(chat):
    chat.monkeypatch.setattr(chat.api, 'REQUEST_TIMEOUT_SECONDS', .02)
    cancelling, finish = threading.Event(), threading.Event()

    async def provider(*args):
        try:
            await asyncio.Event().wait()
        finally:
            cancelling.set()
            while not finish.is_set():
                await asyncio.sleep(.001)

    chat.monkeypatch.setattr(app.state, 'chatbot_provider', provider)
    with ThreadPoolExecutor(1) as pool:
        first = pool.submit(post, chat)
        try:
            assert cancelling.wait(3)
            assert chat.ctx.chat_inflight and app.state.chatbot_budget.inflight == 1
            assert_error(post(chat), 409, 'chat_busy')
        finally:
            finish.set()
        assert_error(first.result(3), 504, 'provider_timeout')
    assert app.state.chatbot_budget.inflight == 0 and not chat.ctx.chat_inflight


def test_provider_failure_after_reset_is_generation_rejection(chat):
    entered, finish = threading.Event(), threading.Event()

    async def provider(*args):
        entered.set()
        while not finish.is_set():
            await asyncio.sleep(.001)
        raise RuntimeError('SECRET_SENTINEL')

    chat.monkeypatch.setattr(app.state, 'chatbot_provider', provider)
    with ThreadPoolExecutor(1) as pool:
        first = pool.submit(post, chat)
        try:
            assert entered.wait(3)
            assert chat.client.post('/api/session/reset').status_code == 200
        finally:
            finish.set()
        response = first.result(3)
    assert_error(response, 409, 'session_changed')
    assert 'SECRET_SENTINEL' not in response.text
    assert not chat.ctx.chat_inflight


def test_broken_sdk_inspection_and_missing_import_never_claim_live(chat):
    chat.monkeypatch.setattr(app.state, 'chatbot_provider', None)
    chat.monkeypatch.setenv('CHATBOT_ENABLED', '1')

    def broken_sdk():
        raise ImportError('SECRET_SENTINEL')
    chat.monkeypatch.setattr(chat.api, '_sdk_available', broken_sdk)
    response = chat.client.get('/api/chatbot/status')
    assert response.status_code == 200 and response.json()['code'] == 'sdk_missing'
    assert 'SECRET_SENTINEL' not in response.text
    chat.monkeypatch.setattr(chat.api, '_sdk_available', lambda: True)
    chat.monkeypatch.setattr(chat.api, '_key_available', lambda: True)
    # A spec alone cannot make the absent real SDK usable in C2.
    assert chat.client.get('/api/chatbot/status').json()['code'] == 'sdk_missing'
    assert_error(post(chat), 503, 'sdk_unavailable')
    assert not chat.calls

@pytest.mark.parametrize('fails,reset', [(False, False), (True, False), (False, True), (True, True)])
def test_deadline_wins_over_provider_suppressed_cancellation(chat, fails, reset):
    chat.monkeypatch.setattr(chat.api, 'REQUEST_TIMEOUT_SECONDS', .01)

    async def provider(*args):
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            if reset:
                chat.ctx.generation = 'new-generation'
            await asyncio.sleep(.03)
            if fails:
                raise RuntimeError('SECRET_SENTINEL')
            return {'code': 'answered', 'answer': 'LATE_REPLY'}

    chat.monkeypatch.setattr(app.state, 'chatbot_provider', provider)
    response = post(chat)
    assert_error(response, 409 if reset else 504, 'session_changed' if reset else 'provider_timeout')
    assert 'LATE_REPLY' not in response.text and 'SECRET_SENTINEL' not in response.text
    assert not chat.ctx.chat_inflight and app.state.chatbot_budget.inflight == 0
    assert len(chat.ctx.chat_attempts) == 1


def test_truncated_answer_must_still_be_nonblank(chat):
    async def provider(*args):
        return {'code': 'answered', 'answer': ' ' * 4096 + 'actual answer'}
    chat.monkeypatch.setattr(app.state, 'chatbot_provider', provider)
    assert_error(post(chat), 502, 'provider_invalid_response')
    assert not chat.ctx.chat_inflight


@pytest.mark.parametrize('method', ['status', 'post'])
def test_lab_lock_contention_does_not_block_chat_event_loop(chat, method):
    from starlette.requests import Request
    from api.session_store import bind_session
    held = threading.Event()

    def lab_work():
        with chat.ctx.lock:
            held.set()
            time.sleep(.2)

    async def run():
        payload = json.dumps({'context_generation': chat.generation, 'message': 'Merkle?',
                              'history': []}).encode()
        async def receive():
            return {'type': 'http.request', 'body': payload, 'more_body': False}
        scope = {'type': 'http', 'method': 'POST', 'path': '/api/chatbot',
                 'scheme': 'http', 'server': ('testserver', 80), 'headers':
                 [(b'content-type', b'application/json')], 'app': app}
        async def heartbeat():
            await asyncio.sleep(.01)
            return time.monotonic()
        with bind_session(chat.ctx):
            start = time.monotonic()
            request = Request(scope, receive)
            operation = chat.api.chatbot_status(request) if method == 'status' else chat.api.chatbot_post(request)
            _, pulse = await asyncio.gather(operation, heartbeat())
            assert pulse - start < .1, 'Chat lock wait blocked unrelated requests'

    with ThreadPoolExecutor(1) as pool:
        worker = pool.submit(lab_work)
        assert held.wait(3)
        asyncio.run(run())
        worker.result(3)


def test_cancelled_quota_admission_cannot_leak_capacity(chat):
    chat.monkeypatch.setattr(chat.api, 'REQUEST_TIMEOUT_SECONDS', .01)
    def slow_admission_clock():
        time.sleep(.05)
        return chat.now[0]
    chat.monkeypatch.setattr(app.state.chatbot_budget, 'clock', slow_admission_clock)
    assert_error(post(chat), 504, 'provider_timeout')
    assert not chat.ctx.chat_inflight and app.state.chatbot_budget.inflight == 0
    assert len(chat.ctx.chat_attempts) == 1
    assert not chat.calls


def test_internal_provider_exception_mapping_is_explicit(chat):
    async def provider(*args):
        raise TimeoutError('SECRET_SENTINEL')
    chat.monkeypatch.setattr(app.state, 'chatbot_provider', provider)
    response = post(chat)
    assert_error(response, 502, 'provider_unavailable')
    assert 'SECRET_SENTINEL' not in response.text
    assert not chat.ctx.chat_inflight and app.state.chatbot_budget.inflight == 0

@pytest.mark.parametrize('fails', [False, True])
def test_reset_during_admission_cleanup_cannot_return_old_result(chat, fails):
    release = app.state.chatbot_budget._release
    def reset_on_release(context):
        context.generation = 'reset-during-cleanup'
        release(context)
    chat.monkeypatch.setattr(app.state.chatbot_budget, '_release', reset_on_release)

    async def provider(*args):
        if fails:
            raise RuntimeError('SECRET_SENTINEL')
        return {'code': 'answered', 'answer': 'OLD_REPLY'}
    chat.monkeypatch.setattr(app.state, 'chatbot_provider', provider)
    response = post(chat)
    assert_error(response, 409, 'session_changed')
    assert 'OLD_REPLY' not in response.text and 'SECRET_SENTINEL' not in response.text
    assert not chat.ctx.chat_inflight and app.state.chatbot_budget.inflight == 0
