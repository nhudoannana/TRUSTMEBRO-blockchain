"""Phase 1 entry routes lead to the existing journey, with no repository mount."""
from html.parser import HTMLParser

from tests.test_mempool_api import client


class Links(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.hrefs = {}
        self.urls = []
        self.start = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a':
            self.urls.append(attrs.get('href'))
            self.hrefs[attrs.get('id', '')] = attrs.get('href')
            if 'start-button' in attrs.get('class', '').split() or 'btn-primary' in attrs.get('class', '').split():
                self.start.append(attrs.get('href'))


def test_entry_routes_follow_mode_choice_to_integrated_journey(client):
    root = client.get('/', follow_redirects=False)
    assert root.status_code == 307
    assert root.headers['location'] == '/landing.html'
    landing = client.get(root.headers['location'])
    assert landing.status_code == 200
    links = Links(landing.text)
    assert links.start and set(links.start) == {'/ui/modes.html'}
    modes = client.get(links.start[0])
    assert modes.status_code == 200
    choices = Links(modes.text)
    journey = client.get(choices.hrefs['guided-mode'])
    assert journey.status_code == 200
    assert choices.hrefs['guided-mode'] == '/ui/trustmebro.html'
    assert 'handlePowMining' in journey.text and '/mining/pow' in journey.text
    assert 'embedded-simulation' not in landing.text and 'srcdoc' not in landing.text
    assert client.get(choices.hrefs['labs-mode'].split('#')[0]).status_code == 200
    assert choices.hrefs['labs-mode'] == '/ui/modes.html#labs'
    assert '/landing.html' in Links(journey.text).urls


def test_entry_static_boundary_and_landing_assets(client):
    landing = client.get('/landing.html').text
    assert 'letter-glitch-canvas' in landing and 'ResizeObserver' in landing
    assert 'cdn.tailwindcss.com' not in landing
    for path in ['/requirements.txt', '/.git/config', '/api/wallet_api.py',
                 '/design-guidelines/TrustMeBro-Blockchain.html']:
        assert client.get(path).status_code == 404


def test_lab_home_links_use_existing_ui_mount(client):
    modes = client.get('/ui/modes.html')
    links = [url for url in Links(modes.text).urls if url and url.startswith('/ui/labs.html#')]
    assert set(links) == {'/ui/labs.html#sha', '/ui/labs.html#signatures', '/ui/labs.html#merkle', '/ui/labs.html#blocks', '/ui/labs.html#consensus', '/ui/labs.html#network', '/ui/labs.html#tamper'}
    for url in links:
        assert client.get(url.split('#')[0]).status_code == 200
    script = client.get('/ui/labs.js')
    assert script.status_code == 200
    assert 'javascript' in script.headers['content-type']


def test_attack_navigation_uses_existing_static_mount(client):
    assert '/ui/attacks.html' in Links(client.get('/ui/modes.html').text).urls
    labs = client.get('/ui/labs.html').text
    assert '/ui/attacks.html' in Links(labs).urls
    assert '/ui/labs.html#tamper' in Links(client.get('/ui/modes.html').text).urls
    page = client.get('/ui/attacks.html')
    assert page.status_code == 200 and '/ui/labs.html' in Links(page.text).urls
    assert client.get('/ui/attacks.js').status_code == 200


def test_explorer_entry_preserves_static_boundary_and_guided_state(client):
    modes = Links(client.get('/ui/modes.html').text)
    assert modes.hrefs['explorer-mode'] == '/ui/explorer.html'
    before = client.get('/api/session').json()
    page = client.get(modes.hrefs['explorer-mode'])
    assert page.status_code == 200
    links = Links(page.text)
    assert '/ui/modes.html#labs' in links.urls and '/ui/trustmebro.html' in links.urls
    assert client.get('/ui/explorer.js').status_code == 200
    assert client.get('/api/network_store.py').status_code == 404
    assert client.get('/api/session').json() == before
