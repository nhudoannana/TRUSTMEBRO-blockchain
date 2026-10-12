"""Context loading/links are runtime trust boundaries; content accuracy is reviewed from source/A3."""
from pathlib import Path

import pytest

from api import chatbot_api as api


def loader():
    value = getattr(api, 'load_context', None)
    assert callable(value), 'Missing bounded curated-context loader'
    return value


def test_curated_asset_is_utf8_bounded_reviewed_and_consumed_without_rewriting():
    path = Path(__file__).resolve().parents[1] / 'docs/CHATBOT_CONTEXT_V1.md'
    assert path.is_file(), 'Missing curated context asset'
    raw = path.read_bytes()
    assert 0 < len(raw) <= 8192 and b'[XM]' not in raw
    assert 'context_version: chatbot-context-v1' in raw.decode('utf-8')
    assert loader()().encode('utf-8') == raw


@pytest.mark.parametrize('data', [b'x' * 8193, b'\xff', b'context_version: other',
    b'context_version: chatbot-context-v1\n[XM] unreviewed'], ids=['oversize', 'utf8', 'version', 'draft'])
def test_invalid_context_fails_closed_without_echo(tmp_path, monkeypatch, data):
    load = loader()
    path = tmp_path / 'context.md'
    path.write_bytes(data)
    monkeypatch.setattr(api, 'CONTEXT_PATH', path)
    with pytest.raises(api.ChatError) as error:
        load()
    assert error.value.code == 'provider_configuration'


def test_missing_context_fails_closed(tmp_path, monkeypatch):
    load = loader()
    monkeypatch.setattr(api, 'CONTEXT_PATH', tmp_path / 'missing.md')
    with pytest.raises(api.ChatError) as error:
        load()
    assert error.value.code == 'provider_configuration'


def test_exact_context_byte_limit_is_valid(tmp_path, monkeypatch):
    load = loader()
    prefix = b'context_version: chatbot-context-v1\n'
    path = tmp_path / 'context.md'
    path.write_bytes(prefix + b' ' * (8192 - len(prefix)))
    monkeypatch.setattr(api, 'CONTEXT_PATH', path)
    assert len(load().encode('utf-8')) == 8192


@pytest.mark.parametrize('query,want', [
    ('Merkle inclusion', ['merkle']), ('RSA-OAEP', ['rsa-oaep']),
    ('RSA-PSS', ['rsa-pss']), ('SHA-256', ['sha']), ('ECDSA', ['signatures']),
    ('C1 C2 C3 credential reorg', ['fork']), ('PoW PoS', ['consensus']),
    ('HTTP network', ['network']), ('tamper', ['tamper']), ('Sybil Eclipse Timejacking', ['attacks']),
    ('Quiz', ['quiz']), ('unknown topic', ['labs']),
])
def test_trusted_topic_links_resolve_to_existing_pages_and_lab_sections(query, want):
    select = getattr(api, 'trusted_lab_links', None)
    assert callable(select), 'Missing trusted link selector'
    links = select(query)
    assert [item['id'] for item in links] == want
    root = Path(__file__).resolve().parents[1]
    for link in links:
        path, _, fragment = link['href'].partition('#')
        assert path.startswith('/') and not path.startswith('//')
        target = root / path.lstrip('/')
        assert target.is_file()
        if fragment:
            assert f'data-lab="{fragment}"' in target.read_text(encoding='utf-8')


def test_links_are_selected_from_question_not_untrusted_url():
    select = getattr(api, 'trusted_lab_links', None)
    assert callable(select), 'Missing trusted link selector'
    links = select('https://evil.invalid javascript:alert(1)')
    assert links == [{'id': 'labs', 'label': 'Các lab', 'href': '/ui/labs.html'}]
