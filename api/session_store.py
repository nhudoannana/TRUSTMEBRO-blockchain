"""RAM-only browser simulations; no authentication or client-selected IDs.

Registry locking covers membership/leases only. A leased request pins its
context; domain operations use that context's locks, never the registry lock.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
import secrets
import threading
import time

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.datastructures import MutableHeaders
from starlette.concurrency import run_in_threadpool

from api.wallet_store import WalletStore

COOKIE_NAME = 'trustmebro_session'
IDLE_SECONDS = 1800
MAX_SESSIONS = 16
_current = ContextVar('trustmebro_simulation')


def current_session():
    """Fail closed outside a resolved request or an explicit internal binding."""
    return _current.get()


@contextmanager
def bind_session(context):
    token = _current.set(context)
    try:
        yield context
    finally:
        _current.reset(token)


@dataclass
class SimulationSession:
    last_used: float
    generation: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    fork_owner: str = field(default_factory=lambda: secrets.token_urlsafe(16))
    lock: object = field(default_factory=threading.RLock, repr=False)
    wallets: WalletStore = field(default_factory=WalletStore, repr=False)
    network: object = field(default=None, repr=False)
    signed_credentials: dict = field(default_factory=dict, repr=False)
    reset_count: int = 0
    active: int = 0
    retiring: bool = False
    block_mining_lock: object = field(default_factory=threading.Lock, repr=False)
    chain_mining_lock: object = field(default_factory=threading.Lock, repr=False)
    lab_keys: dict = field(default_factory=dict, repr=False)
    lab_key_lock: object = field(default_factory=threading.RLock, repr=False)
    lab_networks: dict = field(default_factory=dict, repr=False)
    lab_network_lock: object = field(default_factory=threading.RLock, repr=False)

    def close(self):
        # No registry/node lock while joining workers. Timers use this lab lock.
        with self.lock, self.lab_network_lock, self.lab_key_lock:
            networks = [entry['network'] for entry in self.lab_networks.values()]
            for entry in self.lab_networks.values():
                entry['timer'].cancel()
            if self.network is not None:
                networks.append(self.network)
            for network in networks:
                if hasattr(network, 'close'):
                    network.close()
                else:
                    for node in network.nodes.values():
                        node.stop()
            self.network = None
            self.lab_networks.clear()
            self.lab_keys.clear()
            self.signed_credentials.clear()
            self.wallets.reset_wallets()


class SessionCapacityError(Exception):
    pass


class SessionRegistry:
    def __init__(self, *, clock=time.monotonic, idle_seconds=IDLE_SECONDS, capacity=MAX_SESSIONS):
        self.clock, self.idle_seconds, self.capacity = clock, idle_seconds, capacity
        self.entries = {}
        self.lock = threading.Lock()
        self._stop = threading.Event()
        self._sweeper = None
        self._closing = False

    def _expired_locked(self, now):
        expired = []
        for identifier, context in list(self.entries.items()):
            if not context.active and now - context.last_used >= self.idle_seconds:
                expired.append(self.entries.pop(identifier))
        return expired

    def cleanup(self):
        with self.lock:
            expired = self._expired_locked(self.clock())
        for context in expired:
            context.close()

    def acquire(self, cookie):
        with self.lock:
            now = self.clock()
            expired = self._expired_locked(now)
            context = self.entries.get(cookie) if isinstance(cookie, str) else None
            fresh = context is None
            exhausted = self._closing or (fresh and len(self.entries) >= self.capacity)
            if not exhausted:
                if fresh:
                    cookie = secrets.token_urlsafe(32)
                    context = SimulationSession(now)
                    self.entries[cookie] = context
                context.active += 1
        for old in expired:
            old.close()
        if exhausted:
            raise SessionCapacityError
        return cookie, context, fresh

    def release(self, identifier, context):
        close = False
        with self.lock:
            context.active -= 1
            context.last_used = self.clock()
            if context.retiring and not context.active:
                self.entries.pop(identifier, None)
                close = True
        if close:
            context.close()

    def start(self):
        self._closing = False
        self._stop.clear()
        if self._sweeper is None or not self._sweeper.is_alive():
            self._sweeper = threading.Thread(target=self._sweep, name='simulation-expiry', daemon=True)
            self._sweeper.start()

    def _sweep(self):
        while not self._stop.wait(60):
            self.cleanup()

    def shutdown(self):
        self._stop.set()
        if self._sweeper is not None:
            self._sweeper.join(timeout=1)
        with self.lock:
            self._closing = True
            idle = []
            for identifier, context in list(self.entries.items()):
                context.retiring = True
                if not context.active:
                    idle.append(self.entries.pop(identifier))
        for context in idle:
            context.close()


registry = SessionRegistry()


class SimulationSessionMiddleware:
    """Cookie-only selection for simulation APIs; public visits have no lease.

    Pages serialize their first API calls behind a lightweight bootstrap.
    Resolve HTTPS from ASGI's existing scheme, not untrusted forwarded headers.
    """
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if (scope['type'] != 'http' or not scope['path'].startswith('/api/')
                or scope['path'] in ('/api/health', '/api/health/', '/api/docs', '/api/docs/')):
            return await self.app(scope, receive, send)
        request = Request(scope)
        try:
            identifier, context, fresh = await run_in_threadpool(
                registry.acquire, request.cookies.get(COOKIE_NAME))
        except SessionCapacityError:
            response = JSONResponse(status_code=503, content={'detail': {
                'code': 'session_capacity',
                'message': 'Đã đủ phiên mô phỏng tạm. Hãy thử lại khi phiên không dùng hết hạn.'}},
                headers={'Retry-After': '60'})
            return await response(scope, receive, send)
        cookie = Response()
        if fresh:
            cookie.set_cookie(COOKIE_NAME, identifier, httponly=True, samesite='lax',
                              path='/', secure=scope['scheme'] == 'https')

        async def session_send(message):
            if message['type'] == 'http.response.start':
                headers = MutableHeaders(scope=message)
                headers['X-Simulation-Generation'] = context.generation
                headers['Cache-Control'] = 'no-store'
                if fresh:
                    headers.append('Set-Cookie', cookie.headers['set-cookie'])
            await send(message)

        try:
            with bind_session(context):
                await self.app(scope, receive, session_send)
        finally:
            registry.release(identifier, context)
