"""Owned loopback NetNode servers for the existing retained lab, no public URLs."""
import json
import threading
import urllib.request

from fastapi import HTTPException
from blockchain.net_node import NetNode

HTTP_NETWORK_LIMIT = 4  # Twelve internal listening sockets at most per application process.
_slots = threading.BoundedSemaphore(HTTP_NETWORK_LIMIT)


class HttpLabNetwork:
    transport = 'http'

    def __init__(self, miner):
        self.nodes = {}
        self._closed = False
        self._slots = _slots
        if not self._slots.acquire(blocking=False):
            raise HTTPException(503, detail={'code': 'http_capacity',
                'message': 'Đã đủ mạng HTTP tạm trên server. Đặt lại mạng không dùng hoặc thử lại sau.'},
                headers={'Retry-After': '60'})
        try:
            for i in range(1, 4):
                node = NetNode(f'Node-{i}', '127.0.0.1', 0, [], miner=miner)
                self.nodes[node.node_id] = node  # Own even a partially started server.
                node.start()
            for node in self.nodes.values():
                node.peers = [(peer.node_id, peer.host, peer.port)
                              for peer in self.nodes.values() if peer is not node]
            for node_id in self.nodes:
                self.request(node_id, '/status')
        except Exception as exc:
            self.close()
            raise HTTPException(503, detail={'code': 'http_start_failed',
                'message': 'Không mở được các node HTTP. Tài nguyên tạm đã được dọn; hãy thử lại.'}) from exc

    def request(self, node_id, route, body=None):
        # node_id/route are selected by gateway code, never a client-supplied URL.
        node = self.nodes[node_id]
        request = urllib.request.Request(f'http://127.0.0.1:{node.port}{route}',
            data=json.dumps(body).encode('utf-8') if body is not None else None,
            headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                result = json.load(response)
            node.log(f'HTTP gateway {request.get_method()} {route.split("?")[0]}')
            return result
        except (OSError, ValueError) as exc:
            raise HTTPException(502, detail={'code': 'http_node_unavailable',
                'message': 'Không nhận được phản hồi node HTTP. Làm mới hoặc đặt lại riêng lab.'}) from exc

    def sync_all_nodes(self, *, online_only=True):
        results = []
        for node_id in self.nodes:
            if not online_only or self.request(node_id, '/status')['status'] == 'ONLINE':
                results.append({'node_id': node_id, **self.request(node_id, '/sync', {})})
        return results

    def get_event_log(self):
        return [event for node_id in self.nodes
                for event in self.request(node_id, '/log')['log']][-50:]

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            for node in self.nodes.values():
                node.stop()
        finally:
            self._slots.release()
