"""Public visits never reserve or renew a RAM simulation slot."""
import pytest
from fastapi.testclient import TestClient

from api import session_store
from api.session_store import COOKIE_NAME
from api.wallet_api import app
from tests.test_session_isolation import clocked, context


PUBLIC_PATHS = ['/', '/landing.html', '/ui/modes.html', '/ui/trustmebro.html',
                '/ui/explorer.html', '/ui/labs.html', '/ui/attacks.html',
                '/ui/labs.js', '/ui/tokens.css', '/api/docs', '/docs/oauth2-redirect',
                '/openapi.json', '/api/health']


@pytest.mark.parametrize('path', PUBLIC_PATHS)
def test_public_routes_do_not_allocate_or_refresh_sessions(clocked, path):
    registry, now = clocked
    with TestClient(app) as visitor, TestClient(app) as owner:
        response = visitor.get(path)
        assert response.status_code == 200
        assert not registry.entries and COOKIE_NAME not in visitor.cookies
        assert 'set-cookie' not in response.headers
        owner.get('/api/session')
        current = context(owner)
        used, generation = current.last_used, current.generation
        now[0] = 5
        assert owner.get(path).status_code == 200
        assert current.last_used == used and current.active == 0
        assert current.generation == generation


def test_full_capacity_keeps_public_html_and_existing_apis_accessible(clocked):
    registry, _ = clocked
    registry.capacity = 1
    with TestClient(app) as owner, TestClient(app) as visitor:
        before = owner.get('/api/session').json()
        for path in PUBLIC_PATHS:
            assert visitor.get(path).status_code == 200
        denied = visitor.get('/api/session/bootstrap')
        assert denied.status_code == 503
        assert denied.json()['detail']['code'] == 'session_capacity'
        assert denied.headers['retry-after'] == '60'
        assert COOKIE_NAME not in visitor.cookies
        assert owner.get('/api/session').json() == before
        assert len(registry.entries) == 1


def test_bootstrap_is_cookie_scoped_without_initializing_domain_state(clocked):
    registry, _ = clocked
    with TestClient(app) as client:
        response = client.get('/api/session/bootstrap')
        assert response.status_code == 200
        current = context(client)
        assert response.json()['context_generation'] == current.generation
        assert current.network is None and not current.wallets._store
        assert not current.wallets._seeded
        assert not current.signed_credentials and not current.lab_networks
        identifier = client.cookies.get(COOKIE_NAME)
        assert client.get('/api/session/bootstrap').json() == response.json()
        assert client.cookies.get(COOKIE_NAME) == identifier and len(registry.entries) == 1
        assert client.get('/api/health').json() == {'status': 'ok'}
