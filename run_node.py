"""Khởi chạy một NetNode trong tiến trình riêng.

Cách dùng:
    python run_node.py --node-id Node-1 --port 5001
    python run_node.py --node-id Node-2 --port 5002
    python run_node.py --node-id Node-3 --port 5003

Hoặc dùng run_nodes.py để chạy cả 3 cùng lúc.
"""

import argparse
import signal
import sys
import os

# Thêm thư mục gốc vào path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from blockchain.net_node import NetNode

# Cấu hình mặc định 3 node
ALL_NODES = [
    ("Node-1", "127.0.0.1", 5001),
    ("Node-2", "127.0.0.1", 5002),
    ("Node-3", "127.0.0.1", 5003),
]


def main():
    parser = argparse.ArgumentParser(description="TRUSTMEBRO NetNode")
    parser.add_argument("--node-id", required=True, help="ID node (Node-1, Node-2, Node-3)")
    parser.add_argument("--port", type=int, required=True, help="Port lắng nghe")
    parser.add_argument("--host", default="127.0.0.1", help="Host (mặc định 127.0.0.1)")
    args = parser.parse_args()

    # Tính danh sách peer (tất cả node khác)
    peers = [(nid, h, p) for nid, h, p in ALL_NODES
             if nid != args.node_id]

    node = NetNode(
        node_id=args.node_id,
        host=args.host,
        port=args.port,
        peers=peers,
    )
    node.start()

    print(f"\n{'='*50}")
    print(f"  TRUSTMEBRO {args.node_id} running on {args.host}:{args.port}")
    print(f"  Peers: {', '.join(f'{p[0]}@{p[1]}:{p[2]}' for p in peers)}")
    print(f"  Press Ctrl+C to stop")
    print(f"{'='*50}\n")

    # Xử lý Ctrl+C để dừng sạch
    def shutdown(signum, frame):
        print(f"\n[{args.node_id}] Shutting down...")
        node.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Giữ tiến trình sống
    try:
        while True:
            signal.pause() if hasattr(signal, 'pause') else __import__('time').sleep(1)
    except KeyboardInterrupt:
        shutdown(None, None)


if __name__ == "__main__":
    main()
