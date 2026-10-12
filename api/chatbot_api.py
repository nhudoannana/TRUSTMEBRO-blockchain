"""Bounded, session-owned chat contract. Optional SDK stays lazy and disabled by default."""
import asyncio
from collections import deque
from contextlib import asynccontextmanager
import contextvars
import importlib.util
import json
import logging
import math
import os
import re
import threading
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, StrictStr, Field, ValidationError, model_validator
from typing import Literal

from api.session_store import current_session

logger = logging.getLogger('trustmebro.chatbot')
_current_req_id: contextvars.ContextVar[str | None] = contextvars.ContextVar('chatbot_req_id', default=None)
_current_req_stage: contextvars.ContextVar[str] = contextvars.ContextVar('chatbot_req_stage', default='init')
_current_req_start: contextvars.ContextVar[float | None] = contextvars.ContextVar('chatbot_req_start', default=None)


def _log_diagnostic(req_id, stage, elapsed, *, exc_class=None, status=None, code=None):
    try:
        if isinstance(status, (int, float)):
            status_num = int(status)
        elif hasattr(status, 'value') and isinstance(status.value, int):
            status_num = int(status.value)
        else:
            status_num = None
        elapsed_str = f"{elapsed:.3f}s"
        if exc_class or (code and code not in ('answered', 'blocked')):
            logger.warning(
                "chatbot_diagnostic req_id=%s stage=%s elapsed=%s exc=%s upstream_status=%s code=%s",
                req_id, stage, elapsed_str, exc_class, status_num, code,
            )
        else:
            logger.info(
                "chatbot_diagnostic req_id=%s stage=%s elapsed=%s exc=%s upstream_status=%s code=%s",
                req_id, stage, elapsed_str, exc_class, status_num, code,
            )
    except Exception:
        pass


router = APIRouter(prefix='/api/chatbot', tags=['chatbot'])
BODY_BYTES = 32768
MESSAGE_BYTES = 2048
HISTORY_BYTES = 12288
ANSWER_BYTES = 4096
REQUEST_TIMEOUT_SECONDS = 20
CONTEXT_VERSION = 'chatbot-context-v1'
DEFAULT_MODEL = 'gemini-3.5-flash-lite'

ERRORS = {
    'malformed_json': (400, 'JSON hoặc độ dài request không hợp lệ.'),
    'origin_rejected': (403, 'Hãy gửi câu hỏi từ website cùng nguồn.'),
    'body_too_large': (413, 'Request vượt quá 32.768 byte.'),
    'unsupported_media_type': (415, 'Chỉ nhận JSON không nén.'),
    'invalid_input': (422, 'Kiểm tra nội dung, lịch sử và mã phiên theo giới hạn chatbot.'),
    'sensitive_input': (422, 'Không gửi khóa, ví hoặc dữ liệu lab; hãy hỏi về khái niệm.'),
    'session_changed': (409, 'Phiên đã thay đổi; kết nối lại và bắt đầu hội thoại mới.'),
    'chat_busy': (409, 'Phiên này đang xử lý một câu hỏi.'),
    'chat_rate_limited': (429, 'Phiên đã đạt hạn mức; hãy đợi trước khi hỏi tiếp.'),
    'chat_budget_exhausted': (429, 'Chatbot đã đạt hạn mức máy chủ.'),
    'chat_capacity': (503, 'Chatbot đang đủ lượt xử lý đồng thời.'),
    'chat_disabled': (503, 'Trợ lý AI chưa được bật; các lab vẫn dùng bình thường.'),
    'sdk_unavailable': (503, 'Chưa có thư viện AI tùy chọn; các lab vẫn dùng bình thường.'),
    'key_unavailable': (503, 'Máy chủ chưa cấu hình khóa AI; các lab vẫn dùng bình thường.'),
    'provider_configuration': (503, 'Cấu hình AI chưa hợp lệ; các lab vẫn dùng bình thường.'),
    'provider_timeout': (504, 'AI chưa trả lời kịp; lượt vừa rồi có thể đã dùng hạn mức.'),
    'provider_unavailable': (502, 'AI đang gặp sự cố; hãy thử lại bằng thao tác mới.'),
    'provider_invalid_response': (502, 'AI chưa trả về câu trả lời hợp lệ.'),
}
SENSITIVE = re.compile(
    r'BEGIN[^\r\n]*PRIVATE KEY|AIza[A-Za-z0-9_-]{20,}|[a-fA-F0-9]{64,}|'
    r'[A-Za-z0-9+/=_-]{128,}|'
    r'"(?:private_key|private_key_pem|wallets|transactions|mempool|credential_id|key_handle)"\s*:',
    re.IGNORECASE,
)


class ChatError(Exception):
    def __init__(self, code, retry_after=None, *, stage=None, exc_class=None, upstream_status=None):
        self.code = code
        self.retry_after = retry_after
        self.stage = stage
        self.exc_class = exc_class
        self.upstream_status = upstream_status


def error_response(error):
    status, message = ERRORS[error.code]
    detail = {'code': error.code, 'message': message}
    headers = {}
    if error.retry_after is not None:
        seconds = max(1, math.ceil(error.retry_after))
        detail['retry_after_seconds'] = seconds
        headers['Retry-After'] = str(seconds)
    return JSONResponse(status_code=status, content={'detail': detail}, headers=headers)


def text_bytes(text, limit):
    if not text.strip() or len(text.encode('utf-8')) > limit:
        raise ValueError('Text outside bounds')
    return text


class ChatTurn(BaseModel):
    model_config = {'extra': 'forbid'}
    role: Literal['user', 'assistant']
    content: StrictStr

    @model_validator(mode='after')
    def bounds(self):
        text_bytes(self.content, MESSAGE_BYTES if self.role == 'user' else ANSWER_BYTES)
        return self


class ChatRequest(BaseModel):
    model_config = {'extra': 'forbid'}
    context_generation: StrictStr
    message: StrictStr
    history: list[ChatTurn] = Field(default_factory=list, max_length=6)

    @model_validator(mode='after')
    def bounds(self):
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', self.context_generation):
            raise ValueError('Invalid generation')
        text_bytes(self.message, MESSAGE_BYTES)
        if len(self.history) % 2 or any(
                turn.role != ('user' if i % 2 == 0 else 'assistant')
                for i, turn in enumerate(self.history)):
            raise ValueError('History must contain completed pairs')
        if sum(len(turn.content.encode('utf-8')) for turn in self.history) > HISTORY_BYTES:
            raise ValueError('History outside bounds')
        return self


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key')
        result[key] = value
    return result


async def read_request(request):
    origin = request.headers.get('origin')
    if origin is not None and origin != str(request.base_url).rstrip('/'):
        raise ChatError('origin_rejected')
    if (request.headers.get('content-type', '').split(';')[0].strip().lower() != 'application/json'
            or request.headers.get('content-encoding', 'identity').lower() != 'identity'):
        raise ChatError('unsupported_media_type')
    length = request.headers.get('content-length')
    if length is not None:
        if not re.fullmatch(r'[0-9]+', length):
            raise ChatError('malformed_json')
        if len(length) > 10 or int(length) > BODY_BYTES:
            raise ChatError('body_too_large')
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > BODY_BYTES:
            raise ChatError('body_too_large')
        data.extend(chunk)
    try:
        payload = json.loads(data.decode('utf-8'), object_pairs_hook=_unique_object)
    except (ValueError, UnicodeError, RecursionError):
        raise ChatError('malformed_json') from None
    try:
        body = ChatRequest.model_validate(payload)
    except (ValidationError, ValueError, UnicodeError, RecursionError):
        # Pydantic error repr includes input; never return or log it.
        raise ChatError('invalid_input') from None
    if any(SENSITIVE.search(text) for text in [body.message, *[t.content for t in body.history]]):
        raise ChatError('sensitive_input')
    return body


def _sdk_available():
    try:
        return importlib.util.find_spec('google.genai') is not None
    except (ImportError, ValueError):
        return False


def _key_available():
    return bool(os.environ.get('GEMINI_API_KEY', '').strip())


def availability(provider):
    # Only server-side tests inject a callable. No request can select a provider.
    if callable(provider):
        return 'configured'
    enabled = os.environ.get('CHATBOT_ENABLED', '0')
    if enabled not in ('0', '1'):
        return 'config_invalid'
    if enabled == '0':
        return 'disabled'
    try:
        sdk_ready = _sdk_available()
    except Exception:
        sdk_ready = False
    if not sdk_ready:
        return 'sdk_missing'
    if not _key_available():
        return 'key_missing'
    if os.environ.get('GEMINI_MODEL', DEFAULT_MODEL) != DEFAULT_MODEL:
        return 'config_invalid'
    try:
        _load_sdk()
        load_context()
    except ChatError:
        return 'config_invalid'
    except Exception:
        return 'sdk_missing'
    return 'configured'


# Optional SDK and context are loaded only for an explicitly enabled chatbot.
CONTEXT_PATH = Path(__file__).resolve().parents[1] / 'docs' / 'CHATBOT_CONTEXT_V1.md'
SDK_VERSION = '2.29.0'
GENERATION_TIMEOUT_SECONDS = 15
LAB_TOPICS = (
    ('rsa-oaep', 'RSA · Mã hóa', '/ui/labs.html#rsa-oaep', r'oaep|mã hóa|mã hoá|giải mã|encrypt'),
    ('rsa-pss', 'RSA · Chữ ký', '/ui/labs.html#rsa-pss', r'pss'),
    ('sha', 'SHA-256', '/ui/labs.html#sha', r'sha|hash|băm'),
    ('signatures', 'Chữ ký số', '/ui/labs.html#signatures', r'ecdsa|chữ ký|signature'),
    ('merkle', 'Cây Merkle', '/ui/labs.html#merkle', r'merkle|inclusion|proof'),
    ('fork', 'Fork & Reorg', '/ui/labs.html#fork', r'fork|reorg|credential|nhánh|\bc[123]\b'),
    ('blocks', 'Khối & Chuỗi khối', '/ui/labs.html#blocks', r'block|khối|chuỗi khối'),
    ('consensus', 'PoW–PoS', '/ui/labs.html#consensus', r'\bpow\b|\bpos\b|đồng thuận|consensus'),
    ('network', 'Đồng bộ mạng', '/ui/labs.html#network', r'network|\bhttp\b|mạng|đồng bộ'),
    ('tamper', 'Sửa dữ liệu', '/ui/labs.html#tamper', r'tamper|sửa dữ liệu'),
    ('attacks', 'Tấn công & Phòng vệ', '/ui/attacks.html', r'attack|tấn công|51%|sybil|eclipse|timejack'),
    ('theory', 'Lý thuyết', '/ui/theory.html', r'lý thuyết|theory'),
    ('quiz', 'Quiz', '/ui/quiz.html', r'quiz|trắc nghiệm|ôn tập'),
)


def load_context():
    try:
        with CONTEXT_PATH.open('rb') as source:
            raw = source.read(8193)
        text = raw.decode('utf-8')
    except (OSError, UnicodeError):
        raise ChatError('provider_configuration') from None
    if (not raw or len(raw) > 8192 or '[XM]' in text
            or f'context_version: {CONTEXT_VERSION}' not in text):
        raise ChatError('provider_configuration')
    return text


def trusted_lab_links(message):
    query = message.lower()
    selected = [{'id': key, 'label': label, 'href': href}
                for key, label, href, pattern in LAB_TOPICS if re.search(pattern, query)]
    return selected[:3] or [{'id': 'labs', 'label': 'Các lab', 'href': '/ui/labs.html'}]


def _load_sdk():
    # No SDK body/debug logging, record/replay files, credentials or tools in context.
    logging.getLogger('google_genai').setLevel(logging.CRITICAL)
    logging.getLogger('google_genai._api_client').setLevel(logging.CRITICAL)
    genai = importlib.import_module('google.genai')
    if genai.__version__ != SDK_VERSION:
        raise ChatError('provider_configuration')
    return (genai, importlib.import_module('google.genai.types'),
            importlib.import_module('google.genai.errors'), importlib.import_module('httpx'),
            importlib.import_module('google.genai.client').DebugConfig)


def _sdk_result(response):
    feedback = getattr(response, 'prompt_feedback', None)
    block = getattr(feedback, 'block_reason', None)
    block = getattr(block, 'value', block)
    if block not in (None, '', 'BLOCKED_REASON_UNSPECIFIED'):
        return {'code': 'blocked'}
    candidates = getattr(response, 'candidates', None)
    if not isinstance(candidates, list) or len(candidates) != 1:
        raise ChatError('provider_invalid_response', stage='parse', exc_class='ValueError')
    candidate = candidates[0]
    finish = getattr(candidate, 'finish_reason', None)
    finish = getattr(finish, 'value', finish)
    if finish in ('SAFETY', 'RECITATION', 'BLOCKLIST', 'PROHIBITED_CONTENT', 'SPII'):
        return {'code': 'blocked'}
    if finish not in ('STOP', 'MAX_TOKENS'):
        raise ChatError('provider_invalid_response', stage='parse', exc_class='ValueError')
    parts = getattr(getattr(candidate, 'content', None), 'parts', None)
    if not isinstance(parts, list) or not parts:
        raise ChatError('provider_invalid_response', stage='parse', exc_class='ValueError')
    texts = []
    for part in parts:
        try:
            data = part.model_dump(exclude_none=True)
        except (AttributeError, TypeError, ValueError):
            raise ChatError('provider_invalid_response', stage='parse', exc_class='ValueError') from None
        if not isinstance(data, dict):
            raise ChatError('provider_invalid_response', stage='parse', exc_class='ValueError')
        if data.get('thought') is True:
            continue
        if set(data) - {'text', 'thought', 'thought_signature'} or not isinstance(data.get('text'), str):
            raise ChatError('provider_invalid_response', stage='parse', exc_class='ValueError')
        texts.append(data['text'])
    answer = ''.join(texts)
    if not answer.strip():
        raise ChatError('provider_invalid_response', stage='parse', exc_class='ValueError')
    return {'code': 'answered', 'answer': answer, 'truncated': finish == 'MAX_TOKENS'}


async def _close_sdk(client):
    try:
        await client.aio.aclose()
    finally:
        await asyncio.to_thread(client.close)


async def generate_answer(message, history):
    _current_req_stage.set('client_init')
    try:
        genai, types, errors, httpx, DebugConfig = _load_sdk()
    except ChatError:
        raise
    except Exception as exc:
        raise ChatError('sdk_unavailable', stage='client_init', exc_class=exc.__class__.__name__) from None
    context_text = load_context()
    key = os.environ.get('GEMINI_API_KEY', '').strip()
    if not key:
        raise ChatError('key_unavailable', stage='client_init')
    if os.environ.get('GEMINI_MODEL', DEFAULT_MODEL) != DEFAULT_MODEL:
        raise ChatError('provider_configuration', stage='client_init')
    try:
        contents = [types.Content(role='user' if turn['role'] == 'user' else 'model',
                                  parts=[types.Part(text=turn['content'])]) for turn in history]
        contents.append(types.Content(role='user', parts=[types.Part(text=message)]))
        config = types.GenerateContentConfig(
            system_instruction=context_text, candidate_count=1, max_output_tokens=768,
            response_modalities=['TEXT'],
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            thinking_config=types.ThinkingConfig(thinking_level='MINIMAL', include_thoughts=False))
        creation = asyncio.create_task(asyncio.to_thread(
            genai.Client, api_key=key, enterprise=False,
            debug_config=DebugConfig(client_mode=None, replays_directory=None, replay_id=None),
            http_options=types.HttpOptions(
                base_url='https://generativelanguage.googleapis.com', api_version='v1beta',
                timeout=15000, retry_options=types.HttpRetryOptions(attempts=1),
                client_args={'trust_env': False}, async_client_args={'trust_env': False})))
        try:
            client = await asyncio.shield(creation)
            _current_req_stage.set('transport')
            deadline = asyncio.timeout(GENERATION_TIMEOUT_SECONDS)
            try:
                async with deadline:
                    response = await client.aio.models.generate_content(
                        model=DEFAULT_MODEL, contents=contents, config=config)
            except Exception:
                if deadline.expired():
                    raise ChatError('provider_timeout', stage='transport', exc_class='TimeoutError') from None
                raise
            if deadline.expired():
                raise ChatError('provider_timeout', stage='transport', exc_class='TimeoutError')
        finally:
            try:
                await _finish_worker(creation)
            finally:
                if creation.done() and not creation.cancelled() and creation.exception() is None:
                    await _finish_worker(asyncio.create_task(_close_sdk(creation.result())))
        _current_req_stage.set('parse')
        return _sdk_result(response)
    except ChatError:
        raise
    except (TimeoutError, httpx.TimeoutException) as error:
        raise ChatError('provider_timeout', stage='transport', exc_class=error.__class__.__name__) from None
    except errors.APIError as error:
        status = getattr(error, 'code', None)
        if error.code in (400, 401, 403, 404):
            code = 'provider_configuration'
            retry = None
        elif error.code in (408, 504):
            code = 'provider_timeout'
            retry = None
        else:
            code = 'provider_unavailable'
            retry = 60 if error.code == 429 else None
        raise ChatError(code, retry, stage='transport', exc_class=error.__class__.__name__, upstream_status=status) from None
    except Exception as error:
        status = getattr(error, 'status_code', None) or getattr(getattr(error, 'response', None), 'status_code', None)
        raise ChatError('provider_unavailable', stage=_current_req_stage.get(), exc_class=error.__class__.__name__, upstream_status=status) from None


async def _finish_worker(task):
    # A cancelled waiter must not abandon a quota reservation/release in a worker.
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            continue
    return task.result()


def _generation(context):
    with context.lock:
        return context.generation


def _session_changed(context, generation):
    with context.lock:
        return context.generation != generation or context.retiring


class ChatbotBudget:
    """Process-local spending ceilings; no distributed or durable quota claim."""
    def __init__(self, *, clock=time.monotonic):
        self.clock = clock
        self.lock = threading.Lock()
        self.attempts = deque()
        self.inflight = 0

    def _reserve(self, context, generation):
        # Worker lock order: session -> chat -> process. No provider I/O under locks.
        with context.lock, context.chat_lock, self.lock:
            if context.generation != generation or context.retiring:
                raise ChatError('session_changed')
            now = self.clock()
            while context.chat_attempts and context.chat_attempts[0] <= now - 3600:
                context.chat_attempts.popleft()
            while self.attempts and self.attempts[0] <= now - 86400:
                self.attempts.popleft()
            if context.chat_inflight:
                raise ChatError('chat_busy')
            for window, limit in ((60, 6), (3600, 30)):
                recent = [stamp for stamp in context.chat_attempts if stamp > now - window]
                if len(recent) >= limit:
                    raise ChatError('chat_rate_limited', recent[0] + window - now)
            if self.inflight >= 2:
                raise ChatError('chat_capacity')
            for window, limit in ((3600, 120), (86400, 250)):
                recent = [stamp for stamp in self.attempts if stamp > now - window]
                if len(recent) >= limit:
                    raise ChatError('chat_budget_exhausted', recent[0] + window - now)
            context.chat_attempts.append(now)
            self.attempts.append(now)
            context.chat_inflight = True
            self.inflight += 1
    def _release(self, context):
        with context.chat_lock, self.lock:
            context.chat_inflight = False
            self.inflight -= 1

    @asynccontextmanager
    async def admit(self, context, generation):
        reservation = asyncio.create_task(asyncio.to_thread(self._reserve, context, generation))
        try:
            await asyncio.shield(reservation)
            yield
        finally:
            try:
                await _finish_worker(reservation)
            finally:
                if (reservation.done() and not reservation.cancelled()
                        and reservation.exception() is None):
                    # Keep capacity until the operation and actual worker cleanup both finish.
                    await _finish_worker(asyncio.create_task(asyncio.to_thread(self._release, context)))


@router.get('/status')
async def chatbot_status(request: Request):
    context = current_session()
    generation = await asyncio.to_thread(_generation, context)
    code = await asyncio.to_thread(availability, request.app.state.chatbot_provider)
    return {'code': code, 'configured': code == 'configured', 'provider_verified': False,
            'context_generation': generation, 'context_version': CONTEXT_VERSION,
            'limits': {'message_bytes': MESSAGE_BYTES, 'history_messages': 6,
                       'history_bytes': HISTORY_BYTES, 'answer_bytes': ANSWER_BYTES}}


async def _chatbot_post(request):
    try:
        _current_req_stage.set('ingest')
        body = await read_request(request)
        context = current_session()
        _current_req_stage.set('session_check')
        if await asyncio.to_thread(_session_changed, context, body.context_generation):
            raise ChatError('session_changed', stage='session_check')
        provider = request.app.state.chatbot_provider
        _current_req_stage.set('availability')
        code = await asyncio.to_thread(availability, provider)
        if code != 'configured':
            raise ChatError({'disabled': 'chat_disabled', 'sdk_missing': 'sdk_unavailable',
                             'key_missing': 'key_unavailable',
                             'config_invalid': 'provider_configuration'}[code], stage='availability')
        if not callable(provider):
            provider = generate_answer
        _current_req_stage.set('admit')
        async with request.app.state.chatbot_budget.admit(context, body.context_generation):
            provider_error = None
            try:
                result = await provider(body.message, [turn.model_dump() for turn in body.history])
            except ChatError as error:
                provider_error = error
            except Exception as error:
                # Provider exceptions may contain credentials or request bodies.
                status = getattr(error, 'status_code', None) or getattr(getattr(error, 'response', None), 'status_code', None)
                provider_error = ChatError('provider_unavailable', stage=_current_req_stage.get(), exc_class=error.__class__.__name__, upstream_status=status)
            if await asyncio.to_thread(_session_changed, context, body.context_generation):
                raise ChatError('session_changed', stage='session_check')
            if provider_error is not None:
                raise provider_error
            _current_req_stage.set('format')
            if not isinstance(result, dict) or result.get('code') not in ('answered', 'blocked'):
                raise ChatError('provider_invalid_response', stage='format', exc_class='ValueError')
            response = {'code': result['code'], 'is_ai': True,
                        'context_generation': body.context_generation,
                        'context_version': CONTEXT_VERSION, 'lab_links': trusted_lab_links(body.message),
                        'truncated': False}
            if result['code'] == 'blocked':
                response.update(answer=None, message='AI chưa trả lời nội dung này; hãy hỏi về khái niệm.')
            else:
                answer = result.get('answer')
                if not isinstance(answer, str) or not answer.strip():
                    raise ChatError('provider_invalid_response', stage='format', exc_class='ValueError')
                try:
                    encoded = answer.encode('utf-8')
                except UnicodeError:
                    raise ChatError('provider_invalid_response', stage='format', exc_class='UnicodeError') from None
                response['truncated'] = len(encoded) > ANSWER_BYTES or result.get('truncated') is True
                response['answer'] = encoded[:ANSWER_BYTES].decode('utf-8', errors='ignore')
                if not response['answer'].strip():
                    raise ChatError('provider_invalid_response', stage='format', exc_class='ValueError')
            # Links are backend-owned; provider text/URLs cannot alter the catalog.
            req_id = _current_req_id.get() or 'unknown'
            start = _current_req_start.get() or time.monotonic()
            elapsed = time.monotonic() - start
            _log_diagnostic(req_id, 'complete', elapsed, code=result['code'])
            return response
    except ChatError as error:
        req_id = _current_req_id.get() or 'unknown'
        start = _current_req_start.get() or time.monotonic()
        elapsed = time.monotonic() - start
        stage = error.stage or _current_req_stage.get()
        exc_class = error.exc_class or error.__class__.__name__
        _log_diagnostic(req_id, stage, elapsed, exc_class=exc_class, status=error.upstream_status, code=error.code)
        return error_response(error)


@router.post('')
async def chatbot_post(request: Request):
    req_id = uuid.uuid4().hex[:8]
    start_time = time.monotonic()
    token_id = _current_req_id.set(req_id)
    token_start = _current_req_start.set(start_time)
    token_stage = _current_req_stage.set('ingest')
    try:
        context = current_session()
        generation = context.generation  # Immutable fallback snapshot; locked checks run in workers.
        expired = False

        def deadline_fired():
            nonlocal expired
            expired = True

        timer = asyncio.get_running_loop().call_later(REQUEST_TIMEOUT_SECONDS, deadline_fired)
        try:
            # Covers ingestion too; keep the deadline outcome even if a provider suppresses cancellation.
            result = await asyncio.wait_for(_chatbot_post(request), timeout=REQUEST_TIMEOUT_SECONDS)
            changed = await asyncio.to_thread(_session_changed, context, generation)
            if not expired:
                if changed:
                    elapsed = time.monotonic() - start_time
                    _log_diagnostic(req_id, 'session_check', elapsed, exc_class='ChatError', code='session_changed')
                    return error_response(ChatError('session_changed'))
                return result
        except TimeoutError:
            pass
        finally:
            timer.cancel()
        changed = await asyncio.to_thread(_session_changed, context, generation)
        final_code = 'session_changed' if changed else 'provider_timeout'
        elapsed = time.monotonic() - start_time
        _log_diagnostic(req_id, 'deadline', elapsed, exc_class='TimeoutError', code=final_code)
        return error_response(ChatError(final_code))
    finally:
        _current_req_id.reset(token_id)
        _current_req_start.reset(token_start)
        _current_req_stage.reset(token_stage)
