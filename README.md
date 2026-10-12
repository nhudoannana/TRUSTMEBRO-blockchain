# TRUSTMEBRO — Mô phỏng Blockchain & Hồ sơ số

TRUSTMEBRO là website học tập giúp người dùng phát hành, ký, ghi nhận, xác minh và thu hồi hồ sơ mẫu trên blockchain. Người học có thể đi theo hành trình có hướng dẫn, thực hiện các lab độc lập, đọc lý thuyết và tự kiểm tra kiến thức.

**Công nghệ chính:** Python · FastAPI · HTML/CSS/JavaScript · SHA-256 · ECDSA · RSA · PoW/PoS mô phỏng.

> Đây là mô phỏng giáo dục. Hệ thống không xác minh danh tính hoặc giá trị pháp lý của hồ sơ ngoài đời, không kết nối blockchain công khai và không sử dụng tiền mã hóa thật. Chỉ sử dụng dữ liệu mẫu.

## Nội dung

- [Cài đặt và chạy](#cài-đặt-và-chạy)
- [Hướng dẫn sử dụng](#hướng-dẫn-sử-dụng)
- [Phòng thí nghiệm](#phòng-thí-nghiệm)
- [Chatbot AI](#chatbot-ai)
- [Kiến trúc và mã nguồn](#kiến-trúc-và-mã-nguồn)
- [Phiên và dữ liệu](#phiên-và-dữ-liệu)
- [Kiểm tra](#kiểm-tra)
- [Triển khai](#triển-khai)
- [Giới hạn](#giới-hạn)

## Cài đặt và chạy

### Yêu cầu

- Python; dự án được phát triển với Python 3.13.
- Trình duyệt hiện đại, truy cập bằng localhost hoặc HTTPS để sử dụng Web Crypto.
- Node.js trên PATH nếu chạy các bài test hành vi JavaScript; website không cần npm build.
- Không cần cài cơ sở dữ liệu. Trạng thái mô phỏng được giữ trong RAM.

### Windows / PowerShell

```powershell
git clone --branch main https://github.com/nhudoannana/TRUSTMEBRO-blockchain.git
cd TRUSTMEBRO-blockchain
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn api.wallet_api:app --host 127.0.0.1 --port 8000
```

Các lệnh dùng trực tiếp Python trong môi trường ảo, không cần thay đổi execution policy của PowerShell.

### macOS / Linux

```bash
git clone --branch main https://github.com/nhudoannana/TRUSTMEBRO-blockchain.git
cd TRUSTMEBRO-blockchain
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m uvicorn api.wallet_api:app --host 127.0.0.1 --port 8000
```

Mở **http://127.0.0.1:8000**. Chạy từ thư mục gốc với **một worker**. Không dùng `--reload` khi demo cần giữ trạng thái. Phục vụ giao diện qua FastAPI; mở file HTML trực tiếp hoặc chỉ hosting static không cung cấp backend mô phỏng.

| Trang | Đường dẫn trên cùng server | Chức năng |
|---|---|---|
| Trang chủ | `/landing.html` | Giới thiệu sản phẩm |
| Chọn chế độ | `/ui/modes.html` | Chọn lộ trình học |
| Lý thuyết | `/ui/theory.html` | Bài đọc và liên kết thực hành |
| Có hướng dẫn | `/ui/trustmebro.html` | Quy trình hồ sơ sáu bước |
| Danh sách lab | `/ui/modes.html#labs` | Các thí nghiệm độc lập |
| Block Explorer | `/ui/explorer.html` | Đọc mạng của hành trình có hướng dẫn |
| Tấn công | `/ui/attacks.html` | Ba tình huống kiểm tra phòng vệ |
| Trắc nghiệm | `/ui/quiz.html` | Ôn tập và bài test tổng hợp |
| API docs | `/api/docs` | Swagger UI |
| API schema | `/openapi.json` | Hợp đồng API |
| Health check | `/api/health` | Kiểm tra tiến trình đang phục vụ |

## Hướng dẫn sử dụng

Từ trang chủ, chọn **Bắt đầu mô phỏng**, rồi chọn Lý thuyết, Có hướng dẫn, Phòng thí nghiệm hoặc Trắc nghiệm. Giao diện có công tắc sáng/tối và nút VI/EN; phạm vi nội dung được dịch phụ thuộc từng trang.

### Hành trình có hướng dẫn — sáu bước

| Bước | Thao tác | Điều cần quan sát |
|---|---|---|
| 1. Ví & người phát hành | Chọn hoặc tạo ví người phát hành | Danh tính khóa dùng để ký |
| 2. Phát hành & ký hồ sơ | Nhập dữ liệu mẫu và ký | Hồ sơ và chữ ký gắn với nội dung |
| 3. Gửi vào mempool | Gửi giao dịch đã ký | Giao dịch được kiểm tra và chờ đưa vào block |
| 4. Tạo block | Chọn PoW hoặc PoS, thực hiện tạo block | Nonce/validator và kết quả ghi nhận |
| 5. Đồng bộ mạng | Quan sát node, bật/tắt và đồng bộ | Chiều cao chuỗi, tip hash và bản sao chậm |
| 6. Xác minh & thu hồi | Xác minh hồ sơ, so tài liệu hoặc thu hồi | Trạng thái trên chuỗi và các lớp kiểm tra |

- Xác minh bằng credential ID kiểm tra bản ghi trên chuỗi. Khi so tài liệu trình bày, cần bản ghi `VERIFIED` và `presentation_match=true`; giá trị null nghĩa là chưa so tài liệu.
- Gửi REVOKE vào mempool chưa làm hồ sơ bị thu hồi: giao dịch phải được đưa vào block và truyền tới node cần kiểm tra. Luồng thu hồi có hướng dẫn dùng PoW.
- Chữ ký hợp lệ chứng minh sự phù hợp giữa nội dung và khóa; không chứng minh nội dung đúng ngoài đời.

### Block Explorer

Chọn Node-1/2/3 để đọc block, header và giao dịch ISSUE/REVOKE của **phiên có hướng dẫn hiện tại**. Explorer không xem chuỗi của lab độc lập, không tự đào hoặc đồng bộ. Bấm **Làm mới** sau thao tác; node offline có thể giữ bản sao cũ. Người phát hành và validator PoS là hai vai trò khác nhau.

### Trắc nghiệm

Giao diện hiện tại có **400 câu, 13 chủ đề, ba mức độ**. Có thể luyện theo chủ đề hoặc làm bài tổng hợp **40 câu trong 60 phút**, ngưỡng tự đánh giá đạt từ 70%. Sau khi nộp bài, xem kết quả và đáp án; tiến độ ôn tập lưu cục bộ trong trình duyệt.

Số lượng câu không đồng nghĩa toàn bộ nội dung đã được thẩm định. Repository còn giữ bộ 36 câu được rà soát trước đó trong `ui/quiz_questions.json`; bộ này khác ngân hàng 400 câu của giao diện hiện tại. Chủ đề Bitcoin, UTXO, Ethereum, DeFi hoặc tấn công trong Quiz không đồng nghĩa website đã mô phỏng các chức năng ấy.

## Phòng thí nghiệm

Mỗi lab là thí nghiệm riêng, không phải một mạng sandbox chung. Dùng các tab tìm hiểu/thực hành, nhập dữ liệu mẫu, thực hiện thao tác và đọc kết quả cùng lý do kiểm tra; dùng nút đặt lại của lab để làm lại.

| Lab | Đường dẫn | Thực hành |
|---|---|---|
| SHA-256 | `/ui/labs.html#sha` | So hai văn bản, hash và số bit đầu ra thay đổi |
| RSA-OAEP | `/ui/labs.html#rsa-oaep` | Mã hóa/giải mã, so khóa A/B và ciphertext |
| RSA-PSS | `/ui/labs.html#rsa-pss` | Ký/xác minh, thay thông điệp hoặc khóa |
| Chữ ký ECDSA | `/ui/labs.html#signatures` | Tạo khóa tạm, ký và thử dữ liệu bị sửa |
| Merkle Tree | `/ui/labs.html#merkle` | Dựng cây, sửa lá và kiểm tra inclusion proof |
| Khối & Chuỗi khối | `/ui/labs.html#blocks` | Thêm khối, xem header và sửa khối giữa |
| PoW–PoS | `/ui/labs.html#consensus` | So tạo block trên hai mạng độc lập |
| Đồng bộ mạng | `/ui/labs.html#network` | Node offline, tạo block và đồng bộ; queue/HTTP |
| Fork & Reorg | `/ui/labs.html#fork` | Điều khiển giao tin, phân vùng và nhánh cạnh tranh |
| Sửa dữ liệu | `/ui/labs.html#tamper` | Sửa bản sao Node-2 và phục hồi từ peer hợp lệ |
| Tấn công & Phòng vệ | `/ui/attacks.html` | Sửa sau ký, mạo danh issuer, gửi trùng giao dịch |

### Cách đọc các kết quả quan trọng

- **Merkle:** proof khớp với expected root chỉ chứng minh inclusion theo encoding đó; không tự chứng minh root đáng tin, chữ ký hợp lệ hoặc nội dung đúng. Lab văn bản băm UTF-8 lá, ghép chuỗi hex của hai hash để băm cha, nhân đôi hash cuối ở mức lẻ. Cây văn bản khác cây TxID và cây selective claims.
- **RSA:** RSA-2048; OAEP dùng SHA-256, plaintext tối đa 190 byte UTF-8; PSS dùng SHA-256 và salt 32 byte. Backend xử lý plaintext và khóa riêng, nên đây không phải E2EE.
- **Khối/chuỗi:** tối đa 12 khối ngoài genesis, 4.000 ký tự/khối; difficulty 2–5. Tìm nonce bị giới hạn 200.000 hash hoặc ba giây; chưa tìm được thì không thêm khối. Sửa nội dung giữ bằng chứng cũ để quan sát sai lệch; tính lại hash không tự ký lại, đào lại hoặc sửa các khối sau.
- **Fork:** chọn nhánh hợp lệ có tổng work lớn hơn; PoW tính `16^difficulty` mỗi khối ngoài genesis. Khi hòa work, node giữ nhánh hợp lệ hiện tại, nên các node có thể tạm giữ tip khác nhau. Khối đã biết ngoài nhánh chọn là stale; khối thiếu cha là orphan.
- **Credential reorg:** C1 tách REVOKE nhưng giữ ISSUE → ACTIVE và có thể đưa REVOKE về pending; C2 tách cả ISSUE/REVOKE → chưa có hồ sơ confirmed, ISSUE có thể pending nhưng REVOKE chưa đủ điều kiện; C3 cùng TxID REVOKE còn trên nhánh thắng → vẫn REVOKED, không phục hồi giao dịch ấy vào pool.
- **Attack:** replay là gửi trùng giao dịch, không phải double-spending tiền tệ. Tấn công 51%, Sybil/Eclipse và Timejacking là nội dung lý thuyết, không phải tình huống của attack engine hiện tại.

## Chatbot AI

Widget hỗ trợ giải thích khái niệm và gợi ý lab. Chatbot **không đọc trạng thái ví, node, hồ sơ, lab hay tiến độ Quiz**, không có công cụ thao tác thay người dùng. Nội dung trả lời có thể sai; đối chiếu lý thuyết và kết quả kiểm tra thực tế.

Chatbot mặc định tắt; website và lab vẫn dùng được khi thiếu SDK hoặc API key.

1. Cài dependency tùy chọn trong môi trường riêng:
   ```bash
   python -m pip install -r requirements.txt -r requirements-chatbot.txt
   ```
2. Đặt biến môi trường phía server:

   | Biến | Giá trị / ý nghĩa |
   |---|---|
   | `CHATBOT_ENABLED` | `1` để bật; mặc định `0` |
   | `GEMINI_API_KEY` | Key phía server; không đưa vào frontend hoặc commit |
   | `GEMINI_MODEL` | Không cần đặt; adapter hiện chỉ chấp nhận model mặc định `gemini-3.5-flash-lite` |

3. Khởi động lại server để áp dụng cấu hình. Kiểm tra `/api/chatbot/status`, mở widget, xác nhận gửi dữ liệu theo giao diện rồi hỏi một câu về khái niệm.

`requirements-chatbot.txt` pin `google-genai==2.29.0` và ghi yêu cầu Pydantic ≥2.12.5. Cài SDK có thể thay đổi dependency nền; kiểm tra hồi quy trong môi trường triển khai. Status cấu hình hợp lệ và mocked tests không chứng minh Gemini đang trả lời thật.

Lời hỏi/lịch sử được gửi tới provider khi sử dụng AI; không nhập khóa, cookie, thông tin cá nhân hoặc dữ liệu bí mật. Backend giới hạn input, lịch sử, quota và concurrency; không tự retry. Deadline request là 20 giây.

| Hiện tượng | Cách kiểm tra |
|---|---|
| Chatbot tắt / thiếu cấu hình | Kiểm tra status, biến môi trường và SDK |
| `provider_timeout` | Kiểm tra thời gian và log phía server |
| `provider_unavailable` / HTTP 502 | Tìm `chatbot_diagnostic`; xem stage, exception class, numeric upstream status |
| Hết hạn mức / phiên đang bận | Đợi theo phản hồi trước khi gửi thao tác mới |

Log chẩn đoán không ghi prompt, lịch sử, key, cookie, raw provider body hoặc chuỗi exception. Bản vá log hỗ trợ điều tra lỗi; không tự sửa mọi sự cố provider. Không suy đoán key sai hoặc quota hết chỉ từ HTTP 502.

## Kiến trúc và mã nguồn

Trình duyệt gọi API cùng nguồn. FastAPI giải quyết phiên rồi chuyển thao tác tới wallet/network/lab và blockchain engine; trạng thái mô phỏng nằm trong RAM. Chatbot là nhánh tùy chọn gọi Gemini, tách khỏi quyền đọc trạng thái lab. Quiz giữ tiến độ cục bộ trong trình duyệt.

| Thành phần | Vị trí / trách nhiệm |
|---|---|
| API và static entry | `api/wallet_api.py` |
| Phiên, ví, mạng có hướng dẫn | `api/session_store.py`, `api/wallet_store.py`, `api/network_store.py` |
| RSA / Fork / HTTP lab | `api/rsa_lab.py`, `api/fork_lab.py`, `api/http_network.py` |
| Chatbot | `api/chatbot_api.py`, `docs/CHATBOT_CONTEXT_V1.md`, `ui/chatbot.js` |
| Lõi blockchain | `blockchain/`: hash, wallet, transaction, mempool, Merkle, block, mining, PoS, node, fork |
| Website | `landing.html`, `ui/`: các trang, navbar, theme và bản dịch |
| Kiểm thử | `tests/`: core, API, session, lab và hành vi JavaScript |
| UI Streamlit riêng | `app.py`, `state.py`, `pages/` |
| Quy tắc đóng góp | [AGENTS.md](AGENTS.md) |
| Tài liệu demo/lab | [DEMO_SCRIPT.md](DEMO_SCRIPT.md), [LABS_PHASE1.md](LABS_PHASE1.md); một số phần mang tính lịch sử |

Mật mã dùng `cryptography`: SHA-256, ECDSA secp256k1 và RSA. Mạng chính là ba node trong tiến trình; lab HTTP dùng listener/socket cho mô phỏng, không chứng minh một mạng nhiều máy độc lập đã hoàn thiện.

### Ánh xạ nội dung môn học

| Mục | Nội dung | Mã nguồn chính |
|---|---|---|
| P1 | SHA-256 | `blockchain/hash.py` |
| P2 / P6 | Block và header | `blockchain/block.py` |
| P3 | Chữ ký số | `blockchain/wallet.py`; bổ sung lab RSA |
| P4 | Transaction và mempool | `blockchain/transaction.py`, `blockchain/mempool.py` |
| P5 | Merkle tree/proof | `blockchain/merkle.py`, `blockchain/claim_merkle.py` |
| P7 | PoW | `blockchain/mining.py` |
| P8 | Mạng mô phỏng | `blockchain/node.py`, `blockchain/net_node.py` |
| P9 | Tạo block/đồng thuận | `blockchain/blockchain.py`, `blockchain/pos.py` |
| P10 | Fork/reorg | `blockchain/fork_simulator.py`, `blockchain/fork_transport.py`, `api/fork_lab.py` |
| P11 | Kiểm tra tấn công | API/UI Attack và trang Streamlit riêng |

## Phiên và dữ liệu

Cookie HttpOnly do server tạo dùng để tách mô phỏng, **không phải đăng nhập**. Các tab cùng cookie chia sẻ ví/mạng có hướng dẫn; trình duyệt hoặc profile khác có phiên riêng.

- Reset hành trình chỉ tác động hành trình của phiên đó; lab có dữ liệu/reset riêng.
- Server restart làm mất trạng thái RAM và khóa tạm. Phiên có thể hết hạn sau 30 phút không có request.
- Tối đa 16 phiên sống mỗi tiến trình; khi đầy, phiên mới nhận 503 thay vì đẩy phiên đang hoạt động ra.
- Reload làm mất các dữ liệu giữ trên trang, như snapshot lab khối/chuỗi. Tiến độ Quiz lưu ở localStorage có vòng đời riêng.
- API scripts cần giữ cookie giữa request. API tích hợp không trả khóa riêng của ví.
- Không có database, đồng bộ state giữa worker hoặc tài khoản lưu điểm server-side.

## Kiểm tra

```bash
python -m pytest -q tests
node --check ui/labs.js
node --check ui/rsa_lab.js
node --check ui/fork_lab.js
node --check ui/explorer.js
node --check ui/attacks.js
node --check ui/chatbot.js
node --check ui/quiz.js
git diff --check
```

Trên Windows, thay `python` bằng `.\.venv\Scripts\python.exe` nếu chưa kích hoạt venv. Node.js cần có trên PATH cho test hành vi UI. Chạy phạm vi `tests` để tránh thu thập các bản test lưu làm bằng chứng bên ngoài thư mục này. Không coi số test lịch sử là kết quả của revision hiện tại.

Trước demo, kiểm tra bằng trình duyệt: sáu bước, hai phiên tách biệt, Merkle proof đúng/sai, RSA, sửa khối giữa, Fork/reorg, Attack, Quiz, sáng/tối và màn hình hẹp. Test provider tự động dùng mock; kiểm tra Gemini thật là bước riêng có thể sử dụng quota.

### Streamlit riêng

```bash
python -m streamlit run app.py
```

Thường mở tại http://localhost:8501. UI này có state và các trang riêng; không mặc định chia sẻ cookie/state của FastAPI, và các tình huống Attack có thể khác website tích hợp.

## Triển khai

Với một dịch vụ Python như Render, dùng thư mục gốc repository:

| Thiết lập | Giá trị |
|---|---|
| Build không AI | `pip install -r requirements.txt` |
| Build có AI | `pip install -r requirements.txt -r requirements-chatbot.txt` |
| Start | `uvicorn api.wallet_api:app --host 0.0.0.0 --port $PORT --workers 1` |
| Health path | `/api/health` |

Đặt biến chatbot trong phần Environment phía server, không trong repository. Deploy revision mong muốn và kiểm tra health, lab cũ, chatbot status; một câu trả lời thành công mới kiểm chứng được provider tại thời điểm đó. Restart/redeploy xóa RAM mô phỏng. Chỉ hosting frontend trên Netlify không thay thế dịch vụ API Python.

## Giới hạn

- Đồng thuận và mạng phục vụ học tập, không có bảo đảm bảo mật/độ sẵn sàng của hệ thống production.
- Điểm PoW `16^difficulty` và PoS `1` mỗi khối là quy tắc giáo dục, không tương đương so sánh mức bảo mật.
- PoS cần registry validator đáng tin; kiểm tra chuỗi không replay đầy đủ lịch sử chọn proposer.
- Thời gian PoW/PoS đo trong lab không phải điện năng hoặc kết luận hiệu năng tổng quát.
- HTTP/NetNode đã có, nhưng còn giới hạn reconciliation credential và phục hồi chuỗi lỗi; không suy từ kết quả queue rằng HTTP đã hoàn thiện.
- Một số lab dùng kịch bản cố định. Không có mô phỏng tiền tệ UTXO/double-spending hay tấn công 51% trong attack engine.
- Hồ sơ mẫu là plaintext; RSA lab không làm toàn bộ blockchain được mã hóa và không tạo E2EE.
- Chatbot phụ thuộc provider và có thể timeout/502. Context AI còn nội dung về Quiz 36 câu của bản trước, trong khi UI hiện là 400 câu; cần đối chiếu khi hỏi về phạm vi Quiz.
- Font/video bên ngoài và AI cần mạng; kiểm tra trước khi trình bày offline.
- Cookie mô phỏng không phải hệ thống tài khoản hoặc Google Login được tích hợp.

## Team Members and Responsibilities

| No. | Team Member | Student ID | Role | Assigned Area |
|---:|---|---|---|---|
| 1 | Phạm Thị Hồng Thắm | 031340240027 | Cryptography Engineer | P1 — SHA-256; P3 — ECDSA Digital Signature; P5 — Merkle Tree and Merkle Proof |
| 2 | Đoàn Nguyễn Quỳnh Như | 031340240021 | **Team Leader & Blockchain Engineer** | P2 — Block Structure; P6 — Block Header; P7 — Proof of Work; repository coordination |
| 3 | Cai Thị Thảo Nguyên | 031340240019 | Node & Network Lead | P8 — P2P Network and Multi-Node Simulation |
| 4 | Kiều Thị Yến Nhi | 031340240020 | Mempool & Consensus Engineer | P4 — Transaction Validation and Mempool; P9 — Mining and Distributed Consensus |
| 5 | Huỳnh Thị Tuyết Mai | 031340240016 | Documentation & Report Member | Project report and technical documentation |
| 6 | Trần Quỳnh Ngọc Thảo | 031340240026 | Documentation Support Member | Documentation review and presentation support |
| 7 | Nguyễn Lê Phạm Lộc | 031340240015 | QA & Demo Lead | Testing, demo scenario, video preparation, and P11 — Attack Simulator |


## Tuyên bố học thuật

Sản phẩm được phát triển cho môn Blockchain. Các phép băm, ký và kiểm tra chạy thật trong một mô hình đơn giản hóa; kết quả mô phỏng không cấp chứng nhận pháp lý hoặc bảo đảm bảo mật ngoài thực tế.
