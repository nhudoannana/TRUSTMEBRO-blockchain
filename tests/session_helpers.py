"""Bind white-box assertions to the cookie used by a real TestClient request.

HTTP middleware still resolves every request independently. This only makes
the test thread's direct module inspections refer to that client's context.
"""
from fastapi.testclient import TestClient
from api import session_store


class SessionTestClient(TestClient):
    def request(self, *args, **kwargs):
        response = super().request(*args, **kwargs)
        context = session_store.registry.entries.get(self.cookies.get(session_store.COOKIE_NAME))
        if context is not None:
            session_store._current.set(context)
        return response
