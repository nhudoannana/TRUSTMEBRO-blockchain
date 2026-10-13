"""Logic chatbot TRUSTMEBRO (Gemini) — không phụ thuộc Streamlit để dễ test.

Chatbot biết 3 nguồn:
1. Kiến thức blockchain nói chung (từ mô hình).
2. Tài liệu dự án (README.md + DEMO_SCRIPT.md) — nạp vào system prompt.
3. Dữ liệu thật đang chạy (tool đọc từ Network, chỉ đọc, không sửa).
"""
import json
import time
from pathlib import Path

# Thử lần lượt các model Gemini (gói miễn phí); có thể ép model bằng GEMINI_MODEL trong secrets
DEFAULT_MODELS = ["gemini-flash-lite-latest", "gemini-flash-latest", "gemini-2.5-flash"]
# Các mã lỗi tạm thời / model không có → tự đổi sang model kế tiếp
RETRY_CODES = {404, 429, 500, 503}
ROOT = Path(__file__).parent
DOC_FILES = ["README.md", "DEMO_SCRIPT.md"]
MAX_HISTORY = 10  # số tin nhắn gần nhất gửi kèm mỗi lần hỏi
MAX_DOC_CHARS = 60_000  # giới hạn để prompt không phình quá lớn

INSTRUCTIONS = """Bạn là trợ lý học tập của dự án TRUSTMEBRO — đồ án môn Blockchain
mô phỏng hệ thống xác thực chứng nhận số (SHA-256, ECDSA, Merkle Tree, PoW, PoS,
multi-node consensus, Attack Simulator). Trả lời bằng tiếng Việt, ngắn gọn, dễ hiểu
cho sinh viên; có thể cho ví dụ nhỏ khi cần.

Bạn trả lời được 2 nhóm câu hỏi:
1. Về dự án: cấu trúc code, cách chạy, từng trang, thứ tự demo. Dựa vào TÀI LIỆU DỰ ÁN
   bên dưới; nếu tài liệu không nhắc tới thì nói rõ là không chắc, đừng bịa.
2. Về blockchain nói chung (hash, chữ ký số, Merkle, PoW/PoS, fork, 51%, ví, smart
   contract...). Khi phù hợp, liên hệ với cách dự án này cài đặt khái niệm đó và
   nói rõ chỗ nào dự án đơn giản hoá so với blockchain thật.

Quy tắc:
- Câu hỏi về một Credential ID cụ thể → PHẢI gọi tool verify_credential, không đoán.
- Câu hỏi về trạng thái hiện tại (bao nhiêu block, node nào online, credential nào
  đang ACTIVE/REVOKED...) → gọi tool get_network_status.
- Đây là mô phỏng học tập, không phải blockchain hay tiền mã hoá thật.
- Không yêu cầu hay tiết lộ private key. Nếu câu hỏi ngoài chủ đề dự án và blockchain,
  từ chối lịch sự và đưa người dùng về chủ đề chính."""


def load_project_docs() -> str:
    """Đọc README + DEMO_SCRIPT làm kiến thức về dự án."""
    parts = []
    for name in DOC_FILES:
        path = ROOT / name
        if path.exists():
            parts.append(f"===== {name} =====\n{path.read_text(encoding='utf-8')}")
    return "\n\n".join(parts)[:MAX_DOC_CHARS]


def build_system(docs: str | None = None) -> str:
    """System prompt = hướng dẫn + tài liệu dự án."""
    docs = load_project_docs() if docs is None else docs
    return INSTRUCTIONS + "\n\nTÀI LIỆU DỰ ÁN:\n" + docs


def pick_node(network):
    """Chọn node để đọc dữ liệu. Trả về (tên, node), hoặc (None, None) nếu không có node nào.

    Trang Verify luôn dùng Node-1 nên chatbot cũng ưu tiên Node-1 để hai bên cho cùng kết quả.
    Nếu không có Node-1 thì lấy node ONLINE có height cao nhất.
    """
    if "Node-1" in network.nodes:
        return "Node-1", network.nodes["Node-1"]
    online = [(name, nd) for name, nd in network.nodes.items() if nd.status == "ONLINE"]
    if not online:
        return None, None
    return max(online, key=lambda x: x[1].height)


def get_status(network) -> dict:
    """Snapshot trạng thái mạng — không chứa private key."""
    nodes = []
    for name, node in network.nodes.items():
        nodes.append({
            "node": name,
            "status": node.status,
            "height": node.height,
            "mempool_txs": len(node.mempool.get_transactions()),
        })

    creds: dict[str, str] = {}
    total_txs = 0
    chain_valid = None
    chain_message = "Không có node nào để kiểm tra"
    source_name, rep = pick_node(network)
    if rep is not None:
        chain_valid, bad_idx, chain_message = rep.blockchain.is_chain_valid(
            pos_registry=getattr(network, "pos_registry", None)
        )
        # Chỉ liệt kê credential khi chuỗi hợp lệ: không tin dữ liệu đọc từ chuỗi đã bị sửa
        if chain_valid:
            for block in rep.blockchain.chain:
                for tx in block.transactions:
                    total_txs += 1
                    cid = tx.payload.get("credential_id")
                    if cid:
                        creds[cid] = "ACTIVE" if tx.tx_type == "ISSUE" else (
                            "REVOKED" if tx.tx_type == "REVOKE" else creds.get(cid, "UNKNOWN"))
    result = {
        "nodes": nodes,
        "source_node": source_name,  # node dùng để thống kê bên dưới
        "chain_valid": chain_valid,
        "chain_check": chain_message,
        "confirmed_txs": total_txs,
        "credentials": creds,
    }
    if chain_valid is False:
        result["warning"] = (
            "Chuỗi KHÔNG hợp lệ nên không liệt kê credential. "
            "Hãy báo người dùng chuỗi có dấu hiệu bị sửa đổi và nêu lý do trong chain_check."
        )
    return result


def run_tool(network, name: str, args: dict) -> str:
    if name == "verify_credential":
        node_name, node = pick_node(network)
        if node is None:
            result = {"error": "Không có node nào đang ONLINE để xác minh."}
        else:
            steps, status, info = node.blockchain.verify_credential(
                str(args.get("credential_id", "")).strip(),
                pos_registry=getattr(network, "pos_registry", None),
            )
            result = {
                "checked_on": {"node": node_name, "status": node.status, "height": node.height},
                "status": status,
                "steps": [{"name": n, "passed": p, "detail": d} for n, p, d in steps],
                "info": info,
            }
    elif name == "get_network_status":
        result = get_status(network)
    else:
        result = {"error": f"Tool không tồn tại: {name}"}
    return json.dumps(result, ensure_ascii=False, default=str)


def chat(client, network, history: list[dict], models: list[str] | None = None) -> str:
    """history: [{"role": "user"|"assistant", "content": str}, ...]

    Gemini tự gọi các hàm Python bên dưới khi cần (automatic function calling).
    """
    from google.genai import types  # import trễ để phần logic khác test được không cần SDK

    def verify_credential(credential_id: str) -> dict:
        """Xác minh một credential theo ID trên blockchain (12 bước kiểm tra). Chỉ đọc."""
        return json.loads(run_tool(network, "verify_credential", {"credential_id": credential_id}))

    def get_network_status() -> dict:
        """Lấy trạng thái hiện tại: node, chiều cao chain, mempool, danh sách credential. Chỉ đọc."""
        return get_status(network)

    config = types.GenerateContentConfig(
        system_instruction=build_system(),
        tools=[verify_credential, get_network_status],
    )

    # Chỉ gửi vài lượt gần nhất cho nhanh và đỡ tốn quota,
    # và bảo đảm cuộc hội thoại luôn bắt đầu bằng tin của người dùng.
    recent = history[-MAX_HISTORY:]
    while recent and recent[0]["role"] != "user":
        recent = recent[1:]

    contents = [
        types.Content(
            role="model" if m["role"] == "assistant" else "user",
            parts=[types.Part(text=m["content"])],
        )
        for m in recent
    ]

    last_error = None
    for attempt in range(2):  # 2 vòng: nếu tất cả model đều bận thì đợi chút rồi thử lại
        for model in (models or DEFAULT_MODELS):
            try:
                resp = client.models.generate_content(model=model, contents=contents, config=config)
                return resp.text or "Mình chưa tạo được câu trả lời, bạn thử hỏi lại nhé."
            except Exception as e:
                last_error = e
                if getattr(e, "code", None) not in RETRY_CODES:
                    raise  # lỗi khác (ví dụ key sai) → báo ngay
        if attempt == 0:
            time.sleep(3)
    raise last_error
