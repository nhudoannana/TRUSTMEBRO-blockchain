"""Exercise user-visible workflows, including reruns and reset buttons."""
import pytest
from streamlit.testing.v1 import AppTest
from state import get_network


@pytest.fixture(autouse=True)
def fresh_network():
    get_network.clear()
    yield
    net = get_network()
    for node in net.nodes.values():
        node._running = False
    get_network.clear()


def test_stake_reset_preserves_keys_chain_and_wallet_count():
    app = AppTest.from_file('../pages/12_PoW_vs_PoS.py', default_timeout=30).run()
    assert not app.exception
    net = get_network()
    before = set(net.pos_registry.validators)
    node = net.nodes['Node-1']
    parent = node.blockchain.get_latest_block().compute_hash()
    validator = net.pos_registry.select_validator(1, previous_hash=parent)
    node.blockchain.add_block(net.pos_registry.forge_block(validator, [], 1, parent))
    for _ in range(3):
        app.button(key='btn_reset_pos').click().run()
        assert not app.exception
        assert set(net.pos_registry.validators) == before
        assert len(app.session_state['wallets']) == 3
        assert node.blockchain.is_chain_valid(pos_registry=net.pos_registry)[0]


def test_sign_twice_populates_current_verification_fields():
    app = AppTest.from_file('../pages/2_Wallet.py').run()
    for message in ['First message', 'Second message']:
        app.text_area(key='sign_msg').set_value(message)
        app.button(key='btn_sign').click().run()
        assert not app.exception
        assert app.text_area(key='verify_msg').value == message
        assert app.text_input(key='verify_sig').value == app.session_state['last_signature']
        app.button(key='btn_verify').click().run()
        assert any('VALID' in item.value for item in app.success)


def test_fork_reset_button_works():
    app = AppTest.from_file('../pages/8_Network.py', default_timeout=30).run()
    app.button(key='btn_fork_reset').click().run()
    assert not app.exception
    assert all(n.height == 0 for n in get_network().nodes.values())


def test_brand_on_dashboard():
    app = AppTest.from_file('../app.py').run()
    assert not app.exception
    assert any('TRUSTMEBRO' in title.value for title in app.title)


def test_credential_preset_updates_inputs():
    app = AppTest.from_file('../pages/3_Transaction.py').run()
    preset = app.selectbox(key='domain_preset')
    preset.select(preset.options[1]).run()
    assert app.text_input(key='cred_id').value == 'EXP-DEV-882'


def test_claims_array_is_rejected_without_crashing():
    app = AppTest.from_file('../pages/3_Transaction.py').run()
    app.text_area(key='claims_json').set_value('[1,2]')
    app.button(key='btn_create_tx').click().run()
    assert not app.exception
    assert app.error


def test_created_claims_can_be_submitted_mined_and_verified():
    app = AppTest.from_file('../pages/3_Transaction.py').run()
    app.button(key='btn_create_tx').click().run()
    assert not app.exception
    saved = app.session_state['transactions'][-1]
    app.button(key='submit_created_' + saved['tx_id']).click().run()
    assert not app.exception
    node = get_network().nodes['Node-1']
    assert node.mine_pending(difficulty=1)[0] is not None
    cid = saved['payload']['credential_id']
    bundle = app.session_state['holder_credentials'][cid]
    name, value = next(iter(bundle['claims'].items()))
    assert node.blockchain.verify_selective_claim(cid, name, value, bundle['salts'][name], bundle['proofs'][name])[0]
