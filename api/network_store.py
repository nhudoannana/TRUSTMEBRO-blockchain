"""One guided network per cookie context; use a single Uvicorn worker.

Host/ports label queue-based nodes, without opening sockets.
API handlers hold current_session().lock across wallet access and reset.
No Streamlit dependency.
"""

import secrets
from api.session_store import current_session
from contextlib import ExitStack

from api import wallet_store
from blockchain.node import Network

def _build_network() -> Network:
    network = Network()
    try:
        for i in range(1, 4):
            network.create_node(f"Node-{i}", "127.0.0.1", 5000 + i)
    except Exception:
        for node in network.nodes.values():
            node.stop()
        raise
    return network


def get_network() -> Network:
    with current_session().lock:
        if current_session().network is None:
            current_session().network = _build_network()
        return current_session().network


def reset_network() -> Network:
    with current_session().lock:
        if current_session().network is not None:
            for node in current_session().network.nodes.values():
                node.stop()
        current_session().network = None
        current_session().network = _build_network()
        wallet_store.reset_wallets()
        current_session().signed_credentials.clear()
        current_session().reset_count += 1
        current_session().generation = secrets.token_urlsafe(32)
        return current_session().network


def get_session_info() -> dict:
    with current_session().lock:
        network = get_network()
        return {
            "shared_session": False,
            "nodes": [{"id": n.node_id, "status": n.status} for n in network.nodes.values()],
            "wallet_count": len(wallet_store.list_wallets()),
            "reset_count": current_session().reset_count, "context_generation": current_session().generation,
        }


def get_reset_count() -> int:
    """Read the session generation without seeding or accessing wallets."""
    with current_session().lock:
        return current_session().reset_count


def submit_signed_transaction(network, node, tx) -> tuple[bool, str, str]:
    """Caller holds current_session().lock; workers use node locks, not current_session().lock.

    Hold all node locks in ID order through duplicate scan and admission.
    Node.submit_transaction re-enters its RLock and broadcasts once via queues;
    workers resume after release. No worker acquires another node's state lock.
    """
    # ponytail: lock/scan all demo nodes; index admission if network size matters.
    with ExitStack() as locks:
        nodes = sorted(network.nodes.values(), key=lambda n: n.node_id)
        for peer in nodes:
            locks.enter_context(peer._state_lock)
        if tx.tx_type == "REVOKE" and node.status == "ONLINE":
            credential_id = tx.payload.get("credential_id")
            for peer in nodes:
                if any(pending.tx_type == "REVOKE" and pending.payload.get("credential_id") == credential_id
                       for pending in peer.mempool.get_transactions()):
                    return False, f"Adapter: credential_id '{credential_id}' đã có REVOKE đang chờ tại {peer.node_id}.", "adapter"
        if tx.tx_type == "ISSUE" and isinstance(tx.payload, dict) and node.status == "ONLINE":
            credential_id = tx.payload.get("credential_id")
            for peer in nodes:
                if peer.blockchain.credential_status(credential_id) is not None:
                    return False, f"Adapter: credential_id '{credential_id}' đã tồn tại trong chain của {peer.node_id}.", "adapter"
                if any(pending.tx_type == "ISSUE" and pending.payload.get("credential_id") == credential_id
                       for pending in peer.mempool.get_transactions()):
                    return False, f"Adapter: credential_id '{credential_id}' đã có ISSUE đang chờ tại {peer.node_id}.", "adapter"
        accepted, reason = node.submit_transaction(tx)
        return accepted, reason, "backend"


def get_mempool_snapshots() -> dict:
    """Each node is read under its worker lock; propagation is asynchronous."""
    with current_session().lock:
        rows = []
        for node in get_network().nodes.values():
            with node._state_lock:
                transactions = [tx.to_dict() for tx in node.mempool.get_transactions()]
                rows.append({"node_id": node.node_id, "status": node.status,
                             "pending_count": len(transactions), "transactions": transactions})
        return {"nodes": rows, "reset_count": current_session().reset_count, "context_generation": current_session().generation}


def get_network_snapshots() -> dict:
    """Per-node consistent reads; different nodes are not a globally atomic view."""
    with current_session().lock:
        network = get_network()
        rows = []
        for node in network.nodes.values():
            with node._state_lock:
                valid, invalid_height, reason = node.blockchain.is_chain_valid(
                    pos_registry=network.pos_registry,
                    authorized_issuers=node.mempool.authorized_issuers,
                )
                rows.append({
                    "node_id": node.node_id, "status": node.status,
                    "height": node.height, "block_count": len(node.blockchain.chain),
                    "tip_hash": node.blockchain.get_latest_block().compute_hash() if node.blockchain.chain else None,
                    "pending_count": len(node.mempool.get_transactions()),
                    "chain_valid": valid, "invalid_height": invalid_height, "validity_reason": reason,
                })
        online = [row for row in rows if row["status"] == "ONLINE"]
        agree = bool(online) and len({(row["height"], row["tip_hash"]) for row in online}) == 1
        valid = bool(online) and all(row["chain_valid"] for row in online)
        return {"nodes": rows, "reset_count": current_session().reset_count, "context_generation": current_session().generation,
                "online_nodes_agree": agree, "online_nodes_valid": valid,
                "online_nodes_synchronized": agree and valid,
                "all_nodes_synchronized": agree and valid and len(online) == len(rows),
                "events": network.get_event_log()}
