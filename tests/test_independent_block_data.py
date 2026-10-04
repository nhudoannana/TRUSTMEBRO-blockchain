"""Regression: educational block input must not require certificate metadata."""
from tests.test_mempool_api import client


def test_free_text_without_certificate_fields(client):
    text = '  Ghi chú riêng: 🌏\nKhông phải chứng chỉ.  '
    response = client.post('/api/labs/block/build', json={'data': text, 'difficulty': 2})
    assert response.status_code == 200, response.text
    payload = response.json()['candidate']['transaction']['payload']
    assert payload['lab_data'] == text
    assert set(payload) == {'credential_id', 'lab_data'}

