"""Module state — khởi tạo trạng thái dùng chung cho Streamlit.

Mục đích: tập trung quản lý session_state để tránh lặp code khởi tạo
ở nhiều trang, đảm bảo mọi trang đều thấy cùng một trạng thái.
"""

import streamlit as st


def init_state():
    """Khởi tạo các khoá mặc định trong st.session_state.

    Gọi hàm này ở đầu mỗi trang để đảm bảo session_state luôn có
    đủ các khoá cần thiết, tránh KeyError khi truy cập lần đầu.
    """
    if "wallets" not in st.session_state:
        st.session_state.wallets = []          # danh sách Wallet đã tạo

    if "event_log" not in st.session_state:
        st.session_state.event_log = []        # log sự kiện: list[str]

    # Một nguồn khởi tạo, chạy idempotent trên mọi trang/rerun.
    wallets_by_address = {w["address"]: w for w in st.session_state.wallets}
    for validator in get_network().pos_registry.validators.values():
        wallets_by_address[validator.address] = {
            "name": validator.name,
            "private_key_pem": validator.private_key_pem,
            "public_key_hex": validator.public_key_hex,
            "address": validator.address,
            "source": "validator",
        }
    st.session_state.wallets = list(wallets_by_address.values())


@st.cache_resource
def get_network():
    """Tạo Network với 3 Full Node — chia sẻ giữa mọi trang.

    cache_resource giữ nguyên đối tượng (kể cả thread) qua mọi lần rerun.
    """
    import random
    from blockchain.node import Network
    from blockchain.pos import create_trustprofile_consortium
    net = Network()
    net.create_node("Node-1", "127.0.0.1", 5001)
    net.create_node("Node-2", "127.0.0.1", 5002)
    net.create_node("Node-3", "127.0.0.1", 5003)
    net.pos_registry = create_trustprofile_consortium()
    net.consensus_seed = random.randint(1, 999999)
    return net


def get_pos_registry():
    """Lấy PoSRegistry của liên minh TRUSTMEBRO Consortium dùng chung từ Network."""
    return get_network().pos_registry
