"""Bounded, session-owned chat contract. C1 has no live provider or project context."""
import asyncio
from collections import deque
from contextlib import asynccontextmanager
import importlib.util
import json
import math
import os
import re
import threading
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, StrictStr, Field, ValidationError, model_validator
from typing import Literal

from api.session_store import current_session

router = APIRouter(prefix='/api/chatbot', tags=['chatbot'])
BODY_BYTES = 32768
MESSAGE_BYTES = 2048
HISTORY_BYTES = 12288
ANSWER_BYTES = 4096
REQUEST_TIMEOUT_SECONDS = 20
CONTEXT_VERSION = 'chatbot-context-v1'  # Reserved contract version; C2 supplies the context.
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
    def __init__(self, code, retry_after=None):
        self.code, self.retry_after = code, retry_after


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
    return 'disabled'  # C1 deliberately has no Gemini adapter, even with SDK/key present.


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
    code = availability(request.app.state.chatbot_provider)
    return {'code': code, 'configured': code == 'configured', 'provider_verified': False,
            'context_generation': generation, 'context_version': CONTEXT_VERSION,
            'limits': {'message_bytes': MESSAGE_BYTES, 'history_messages': 6,
                       'history_bytes': HISTORY_BYTES, 'answer_bytes': ANSWER_BYTES}}


async def _chatbot_post(request):
    try:
        body = await read_request(request)
        context = current_session()
        if await asyncio.to_thread(_session_changed, context, body.context_generation):
            raise ChatError('session_changed')
        provider = request.app.state.chatbot_provider
        code = availability(provider)
        if code != 'configured':
            raise ChatError({'disabled': 'chat_disabled', 'sdk_missing': 'sdk_unavailable',
                             'key_missing': 'key_unavailable',
                             'config_invalid': 'provider_configuration'}[code])
        async with request.app.state.chatbot_budget.admit(context, body.context_generation):
            provider_error = None
            try:
                result = await provider(body.message, [turn.model_dump() for turn in body.history])
            except Exception:
                # Provider exceptions may contain credentials or request bodies.
                provider_error = ChatError('provider_unavailable')
            if await asyncio.to_thread(_session_changed, context, body.context_generation):
                raise ChatError('session_changed')
            if provider_error is not None:
                raise provider_error
            if not isinstance(result, dict) or result.get('code') not in ('answered', 'blocked'):
                raise ChatError('provider_invalid_response')
            response = {'code': result['code'], 'is_ai': True,
                        'context_generation': body.context_generation,
                        'context_version': CONTEXT_VERSION, 'lab_links': [],
                        'truncated': False}
            if result['code'] == 'blocked':
                response.update(answer=None, message='AI chưa trả lời nội dung này; hãy hỏi về khái niệm.')
            else:
                answer = result.get('answer')
                if not isinstance(answer, str) or not answer.strip():
                    raise ChatError('provider_invalid_response')
                try:
                    encoded = answer.encode('utf-8')
                except UnicodeError:
                    raise ChatError('provider_invalid_response') from None
                response['truncated'] = len(encoded) > ANSWER_BYTES
                response['answer'] = encoded[:ANSWER_BYTES].decode('utf-8', errors='ignore')
                if not response['answer'].strip():
                    raise ChatError('provider_invalid_response')
            # C2 supplies curated, server-owned links. Provider URLs are never trusted.
            return response
    except ChatError as error:
        return error_response(error)


@router.post('')
async def chatbot_post(request: Request):
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
            return error_response(ChatError('session_changed')) if changed else result
    except TimeoutError:
        pass
    finally:
        timer.cancel()
    changed = await asyncio.to_thread(_session_changed, context, generation)
    return error_response(ChatError('session_changed' if changed else 'provider_timeout'))
