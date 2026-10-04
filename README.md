# TRUSTMEBRO — Blockchain-Based Verifiable Profile & Credential System

> An educational blockchain simulation that demonstrates how digital credentials can be issued, verified, and protected from tampering using SHA-256 hashing, ECDSA digital signatures, Merkle Trees, Proof of Work, and multi-node consensus.

## Overview

TRUSTMEBRO models a complete credential lifecycle on a simplified blockchain:

1. An **Issuer** creates a digital credential for a **Holder** (e.g., a university degree).
2. The credential is packaged into a **Transaction** and signed with an **ECDSA (SECP256K1) digital signature**.
3. A **Node** validates the transaction (format, signature, issuer registry, credential status) before accepting it into its **Mempool**.
4. A **Miner** packages valid transactions into a **Block**, computing a **Merkle Root** and solving a **Proof of Work** puzzle.
5. **Three full nodes** independently validate, broadcast, and reach consensus on the blockchain state.
6. A **Verifier** can check any credential by its Credential ID through a 12-step verification process.
7. An **Attack Simulator** demonstrates six classes of tampering and shows exactly which protection layer detects each one.

> **Note:** This is an educational simulation built for an academic blockchain course. It does not connect to any public blockchain, does not use real cryptocurrency, and is not designed for production use.

## Project Objectives

Demonstrate the end-to-end flow of blockchain-based credential management:

```
SHA-256 → Digital Signature → Transaction → Mempool → Merkle Tree
  → Block → Proof of Work → Network → Consensus → Credential Verification → Attack Detection
```

## Key Features

| Feature | Description |
|---|---|
| SHA-256 Hashing | Hash generation, Avalanche Effect comparison, brute-force simulation |
| ECDSA Wallets | Key pair generation (SECP256K1), message signing, signature verification |
| Credential Transactions | Issue and Revoke transactions with canonical JSON hashing |
| Transaction Validation | 5-step mempool validation (format, signature, duplicate, registry, ledger status) |
| Merkle Tree | Tree construction, Merkle Root calculation, Merkle Proof generation and verification |
| Block & Blockchain | Block creation with 6-field header, chain validation (hash linkage, Merkle Root, PoW) |
| Proof of Work | Nonce-based mining with configurable difficulty (2–5), benchmark comparison |
| Multi-Node Network | Three full nodes with independent blockchain, mempool, and daemon worker threads |
| Mining & Consensus | End-to-end flow: TX → Mempool → Mine → Block broadcast → Node validation → Consensus |
| Credential Verification | 12-step verification with pass/fail detail for each step |
| Credential Revocation | Revoke credentials via REVOKE transactions (Mempool → Mine → Blockchain) |
| Attack Simulator | Six tamper scenarios running on deep copies, each showing which layer catches the attack |

## Technology Stack

| Component | Version / Detail |
|---|---|
| Python | 3.13.7 |
| Streamlit | ≥ 1.30.0 (tested with 1.64.0) |
| cryptography | ≥ 42.0.0 (ECDSA SECP256K1) |
| pytest | ≥ 8.0.0 |
| Standard library | `hashlib`, `json`, `threading`, `queue`, `copy`, `time`, `datetime` |

No database is used. All data is stored in memory.

## Installation (Windows)

```bash
git clone https://github.com/nhudoannana/trustprofile-blockchain.git
cd trustprofile-blockchain
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

> **PowerShell users:** If script execution is blocked, run `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned` or activate the virtual environment from Command Prompt (`cmd`) instead.

## Running the Application

Integrated frontend (completed A–G credential journey):

```bash
python -m uvicorn api.wallet_api:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`. Use a **single Uvicorn worker** (the default);
multiple workers create separate in-memory sessions. Do not use `--reload` on
demo day because it wipes in-memory state on every file save. All users share
one queue-based Network (Node-1/2/3; ports 5001/5002/5003 are labels only).
“Bắt đầu lại” resets the network and all wallets, then generates fresh demo
wallets. The A–G journey supports signing, mempool submission, PoW mining,
sync/offline catch-up, verification, presentation comparison and revocation.
The brand opens `http://127.0.0.1:8000/landing.html`; its entry buttons return
to `http://127.0.0.1:8000/ui/trustmebro.html`.

Verification by ID checks the on-chain record only (`record_verified`). A
presented document is accepted only with VERIFIED and `presentation_match=true`
(`presented_document_accepted`). `presentation_match=null` means no comparison.
The legacy `success` field remains compatible and is not proof that a document
was compared. Issuer identity comes from verified ISSUE metadata, not the
currently selected wallet or a PoS validator.

The separate Streamlit learning interface:

```bash
streamlit run app.py
```

Streamlit typically opens at `http://localhost:8501` in the default browser.

## Running the Tests

Install Python dependencies with `python -m pip install -r requirements.txt`.
**Node.js must also be installed and `node` available on PATH**: the existing
JavaScript UI tests execute the real inline handlers using Node's VM. These
tests are required and are not skipped when Node is missing. Check `node --version`.

```bash
python -m pytest -q
```

The reviewed A–G tree passed **282 tests** before these completion fixes.
Run the suite above to validate your current tree; test totals change with regressions.

## Project Structure

```
trustprofile/
├── app.py                          # Streamlit entry point — Dashboard + st.navigation
├── state.py                        # Session state initialization + shared Network (cache_resource)
├── requirements.txt
├── README.md
├── DEMO_SCRIPT.md
│
├── blockchain/                     # Core engine (no Streamlit dependency)
│   ├── __init__.py
│   ├── hash.py                     # sha256_hex, bit_difference_percent, bruteforce
│   ├── wallet.py                   # Wallet dataclass, generate_wallet, sign/verify
│   ├── transaction.py              # Credential dataclass, Transaction class, verify_transaction
│   ├── mempool.py                  # Mempool class (5-step validation), DummyLedger
│   ├── merkle.py                   # build_merkle_tree, merkle root/proof/verify
│   ├── block.py                    # BlockHeader dataclass (6 fields), Block class
│   ├── blockchain.py               # Blockchain class — chain management, credential ledger, 12-step verify
│   ├── mining.py                   # mine_block (PoW), is_valid_pow
│   └── node.py                     # Node class (worker thread), Network class (broadcast, event log)
│
├── pages/                          # Streamlit pages (loaded via st.navigation)
│   ├── 1_Hash_Demo.py              # SHA-256 — hash, Avalanche Effect, brute-force
│   ├── 2_Wallet.py                 # Wallet creation, signing, verification, tamper demo
│   ├── 3_Transaction.py            # Credential + Transaction creation, signing, validation
│   ├── 4_Mempool.py                # Mempool management, attack demos (tampered, unauthorized, duplicate)
│   ├── 5_Merkle.py                 # Merkle Tree visualization, tamper detection, Merkle Proof
│   ├── 6_Explorer.py               # Blockchain Explorer — block detail, tamper & recompute demo
│   ├── 7_Mining.py                 # PoW mining, difficulty benchmark
│   ├── 8_Network.py                # 3-node status, TX broadcast, online/offline, sync
│   ├── 9_Mining_Flow.py            # End-to-end: Submit TX → Mine → Consensus
│   ├── 10_Verify.py                # 12-step credential verification, revocation, history
│   └── 11_Attacks.py               # 6 attack scenarios on deep copies
│
├── tests/                          # pytest test suite (51 tests)
│   ├── __init__.py
│   ├── test_hash.py                # 9 tests
│   ├── test_wallet.py              # 4 tests
│   ├── test_transaction.py         # 6 tests
│   ├── test_mempool.py             # 5 tests
│   ├── test_merkle.py              # 6 tests
│   ├── test_blockchain.py          # 6 tests
│   ├── test_mining.py              # 5 tests
│   ├── test_node.py                # 4 tests
│   ├── test_consensus.py           # 3 tests
│   └── test_verify.py              # 3 tests
│
├── pages_archive/                  # Archived placeholder pages from initial scaffold
│   └── (6 placeholder files)
│
└── docs/
    └── images/                     # Screenshots (to be added after final UI review)
```

## Implementation Map: P1–P11

| Project Item | Topic | Implementation File(s) | Demo Page | Test File(s) | Status |
|---|---|---|---|---|---|
| P1 | SHA-256 Hash | `blockchain/hash.py` | SHA-256 (`1_Hash_Demo.py`) | `test_hash.py` (9 tests) | ✅ Implemented |
| P2 | Block Structure | `blockchain/block.py` | Blockchain Explorer (`6_Explorer.py`) | `test_blockchain.py` (6 tests) | ✅ Implemented |
| P3 | ECDSA Digital Signature | `blockchain/wallet.py` | Wallet & Digital Signature (`2_Wallet.py`) | `test_wallet.py` (4 tests) | ✅ Implemented |
| P4 | Transaction & Mempool | `blockchain/transaction.py`, `blockchain/mempool.py` | Credentials & Transactions (`3_Transaction.py`), Mempool (`4_Mempool.py`) | `test_transaction.py` (6), `test_mempool.py` (5) | ✅ Implemented |
| P5 | Merkle Tree | `blockchain/merkle.py` | Merkle Tree (`5_Merkle.py`) | `test_merkle.py` (6 tests) | ✅ Implemented |
| P6 | Block Header (6 fields) | `blockchain/block.py` | Blockchain Explorer (`6_Explorer.py`) | `test_blockchain.py` (6 tests) | ✅ Implemented |
| P7 | Proof of Work | `blockchain/mining.py` | Proof of Work / Mining (`7_Mining.py`) | `test_mining.py` (5 tests) | ✅ Implemented |
| P8 | P2P Network | `blockchain/node.py` | Network (`8_Network.py`) | `test_node.py` (4 tests) | ✅ Implemented |
| P9 | Mining & Consensus | `blockchain/node.py`, `blockchain/blockchain.py` | Mining & Consensus Flow (`9_Mining_Flow.py`) | `test_consensus.py` (3 tests) | ✅ Implemented |
| P10 | Fork / Chain Split | `blockchain/node.py` (`_handle_block`, `_handle_sync_response`) | Network (`8_Network.py`) | No dedicated test | Partially implemented |
| P11 | Attack Simulator | `pages/11_Attacks.py` | Attack Simulator (`11_Attacks.py`) | No dedicated test (attacks run on UI deep copies) | ✅ Implemented |

**P10 Note:** The system detects a `previous_hash` mismatch and triggers `sync_chain`, which applies the longest-valid-chain rule. It does not implement full fork resolution (e.g., comparing competing chains at equal height, orphan block storage, or chain reorganization). This is a deliberate simplification for educational purposes.

## End-to-End Demo Flow

1. **Create an Issuer wallet** — Open *Wallet & Digital Signature*, enter a name (e.g., "Trường Đại học A"), click *Generate Wallet*.
2. **Create and sign a credential transaction** — Open *Mining & Consensus Flow*, select the Issuer wallet, fill in Credential ID / Holder / Title, click *Create → Sign → Submit → Broadcast*.
3. **Broadcast the transaction** — The transaction is automatically broadcast to all online nodes upon submission.
4. **Inspect the mempool** — Open *Network*, expand a node's detail to see pending transactions in its mempool.
5. **Mine a block** — On *Mining & Consensus Flow*, select a miner node, set difficulty, click *Mine Block*.
6. **Confirm consensus** — After mining, the status table shows all three nodes with the same Height and Tip Hash.
7. **Verify the credential** — Open *Verify Credential*, enter the Credential ID, click *Verify*. A 12-step verification report appears.
8. **Attack Simulator** — Open *Attack Simulator*, run any of the six scenarios to see which protection layer detects the tamper.

## Test Coverage

| Test File | Module Tested | Tests |
|---|---|---|
| `test_hash.py` | `blockchain/hash.py` | 9 |
| `test_wallet.py` | `blockchain/wallet.py` | 4 |
| `test_transaction.py` | `blockchain/transaction.py` | 6 |
| `test_mempool.py` | `blockchain/mempool.py` | 5 |
| `test_merkle.py` | `blockchain/merkle.py` | 6 |
| `test_blockchain.py` | `blockchain/block.py`, `blockchain/blockchain.py` | 6 |
| `test_mining.py` | `blockchain/mining.py` | 5 |
| `test_node.py` | `blockchain/node.py` | 4 |
| `test_consensus.py` | End-to-end consensus flow | 3 |
| `test_verify.py` | Credential verification & revocation | 3 |
| **Total** | | **51** |

The Attack Simulator (`pages/11_Attacks.py`) runs six tamper scenarios interactively on deep copies of the blockchain. These are demonstrated through the UI and do not have a separate pytest file.

## Project Limitations

- **In-memory storage.** All blockchain data, wallets, and mempool state reside in memory and are lost when the Streamlit process restarts.
- **Simulated network.** Node communication uses in-process queues; port numbers (5001/5002/5003) are logical labels and no real TCP sockets are opened.
- **No public blockchain.** The project does not connect to any external blockchain or use real cryptocurrency.
- **Simplified consensus.** Fork handling uses a longest-valid-chain replacement strategy triggered by `previous_hash` mismatch. Full fork resolution, orphan block management, and chain reorganization are not implemented.
- **No privacy controls.** Credential data is stored in plaintext in the blockchain. Sensitive personal information should not be placed on a public blockchain without additional privacy mechanisms.
- **Authenticity, not truth.** The blockchain can prove who signed a credential and whether the data has been altered. It cannot independently verify that the original credential content was factually correct.
- **Educational purpose only.** This application is not designed for production use.

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

## Screenshots

> Screenshots will be added after the final UI review. The following placeholders indicate which views will be captured.

<!--
![Dashboard](docs/images/dashboard.png)
![Wallet and Digital Signature](docs/images/wallet-signature.png)
![Mining](docs/images/mining.png)
![Network Consensus](docs/images/network-consensus.png)
![Credential Verification](docs/images/verify-credential.png)
![Attack Simulator](docs/images/attack-simulator.png)
-->

| View | Path |
|---|---|
| Dashboard | `docs/images/dashboard.png` |
| Wallet & Digital Signature | `docs/images/wallet-signature.png` |
| Mining | `docs/images/mining.png` |
| Network Consensus | `docs/images/network-consensus.png` |
| Credential Verification | `docs/images/verify-credential.png` |
| Attack Simulator | `docs/images/attack-simulator.png` |

## Educational Notice

This repository was developed as a group project for an academic blockchain course. It demonstrates core blockchain mechanisms — hashing, digital signatures, Merkle Trees, Proof of Work, peer-to-peer consensus, and tamper detection — in a controlled simulation environment. It is not intended for production use or real-world credential issuance.

### Lưu ý sau bản sửa PoS (review vòng 3)

- Hash/chữ ký PoS bao gồm `height` để chống sửa bằng chứng ký kép. Block PoS
  tạo bằng phiên bản cũ cần tạo lại; khởi động lại ứng dụng để reset mạng demo trong RAM.
- Khi gọi `is_chain_valid`, `verify_credential` hoặc `verify_selective_claim` cho
  chuỗi có PoS, truyền `pos_registry=network.pos_registry`. Thiếu registry sẽ bị từ chối.
- Benchmark chỉ đo thời gian tạo khối rỗng và số lần thử nonce PoW, chưa đo điện năng.
- Quy tắc sửa code theo Karpathy guidelines được ghi trong [AGENTS.md](AGENTS.md).

### Backend validation (review round 4)

- Block reception, forks, sync and local production validate transaction signatures
  and apply ledger rules in order. Only the original issuer can revoke an active credential.
- Credential IDs are unique for the lifetime of a branch. Reissuing after revocation
  requires a new ID. Conflicting pending transactions cause block production to be
  rejected without changing the chain or deleting the pending transactions.
- Reorganization updates the block pool so the node can receive the next block.
  Sync all selects a valid source and preserves normal validation and mempool handling.
- PoS blocks require zero difficulty and nonce. The mixed demo awards 1 point per PoS
  block and `16 ** difficulty` per PoW block; this is an educational scoring rule,
  not a production hybrid consensus protocol.

### Guided journey PoS integration

Run `python -m uvicorn api.wallet_api:app --host 127.0.0.1 --port 8000`
and open http://127.0.0.1:8000/ui/trustmebro.html. Step 4 defaults to PoW;
PoS is an optional choice. Step 6 keeps explicit PoW mining for revocation.

- `GET /api/consensus/pos?node_id=Node-1` returns public validator identities,
  eligibility, stake, selection weights, stake mode, seed, next height/parent
  and a **provisional** backend prediction. Weights are not guaranteed frequencies.
  A different chain tip can change the actual signer.
- `POST /api/mining/pos` accepts only `{"node_id":"Node-1"}`. The backend
  selects the validator, signs, validates, appends and queue-broadcasts once.
  The response contains `forged`, a verbatim backend rejection `reason`, canonical
  `block`, `transaction_ids`, public `signer` (including stake/weight), `seconds`,
  `elapsed_scope`, and `reset_count`. Time measures the complete
  `forge_pos_pending` call, excluding API lock acquisition and peer propagation.
  It is not an energy measurement or a nonce-search count.
- Unknown nodes return 404. Offline/empty/no-eligible/candidate failures return
  `forged=false` without deleting pending transactions. Unexpected exceptions
  return 500. Both APIs return full public keys/addresses, never private keys.
- Session then sorted node locks coordinate these API operations with reset,
  submission, mining and node workers. Signer metadata belongs to the same registry
  and session as forging. No locks are held waiting for peer propagation.

Existing simulation limitations are preserved:

- Guided issuer wallets and validator wallets have distinct keys, even with equal
  display names. Guided issuance does not increase validator stake; this integration
  does not call `sync_with_blockchain`, so the current selection weights stay stable.
- The registry holds validator private signing keys in one server process. These
  are simulated validators, not independently secured machines.
- Live PoS reception checks the rightful proposer, but full-chain validation and
  credential verification validate registry signatures without replaying historical
  validator selection. A trusted registry is required.
- Mixed-chain fork scores remain `16 ** difficulty` for each PoW block and 1 for
  each PoS block; the two block types are not equally weighted.
- Reset/restart clears in-memory demo state and creates fresh identities. ID-only
  VERIFIED verifies the on-chain record; presented-document acceptance additionally
  requires `presentation_match=true`. No comparison keeps it null.

### TRUSTMEBRO app review

Block Explorer: http://127.0.0.1:8000/ui/explorer.html — **Xem blockchain của phiên
mô phỏng có hướng dẫn.** Chọn Node-1/2/3 để đọc chuỗi chính (gồm genesis), header
PoW/PoS và payload/chữ ký ISSUE hoặc REVOKE. Tạo một block trong journey, mở Explorer,
chọn block rồi xem giao dịch. Sau thay đổi/reset, bấm **Làm mới**; không có polling.
Explorer chỉ đọc dữ liệu; không tạo block hay đồng bộ node, và không xem mạng lab
cô lập. Node offline vẫn đọc được nhưng có cảnh báo dữ liệu cũ. Danh tính issuer
và validator hiển thị riêng; tên validator chỉ lấy từ registry khi khóa khớp chữ ký.
GET `/api/explorer/blocks?node_id=Node-1` trả snapshot và các block mới nhất trước;
GET `/api/explorer/blocks/{height}?node_id=Node-1` trả header/giao dịch public.
Hash hiển thị không thay thế việc xác minh chuỗi. Đây là trạng thái trong bộ nhớ
của phiên trình duyệt trong tiến trình FastAPI; reset chỉ đổi dữ liệu phiên này,
không đổi cookie. Restart hoặc hết hạn tạo cookie và generation mới.

### Phiên mô phỏng riêng cho trình duyệt

Hành trình có hướng dẫn và Explorer dùng cookie opaque do server sinh ngẫu nhiên
(`trustmebro_session`, HttpOnly, SameSite=Lax, Path=/; Secure khi ASGI chạy HTTPS).
HTTP localhost vẫn được hỗ trợ; không thay cấu hình tin cậy proxy. Không chọn
phiên bằng query, JSON hay header tự đặt. Đây là phạm vi mô phỏng, không phải login.
Các tab cùng cookie dùng chung ví/network; profile hoặc incognito có cookie khác
thì tách biệt. Reset chỉ đổi network, ví, hồ sơ đã ký, reset_count và generation
của cookie hiện tại. Nó không reset lab riêng, cũng không ảnh hưởng trình duyệt khác.

RAM có tối đa **16 phiên**, hết hạn sau **30 phút không có request**. Request đang
chạy giữ lease nên không bị dọn giữa lượt đào; lock registry chỉ bảo vệ membership,
không giữ khi ký/đào/sync. Cleanup khi truy cập và mỗi 60 giây dừng node worker,
hủy timer lab và xóa khóa/ví; shutdown cũng dọn, chờ request đang chạy giải phóng lease.
Hết capacity sau cleanup trả 503 với `detail.code=session_capacity` và Retry-After,
không xóa phiên đang dùng. Cookie thiếu/giả/hết hạn nhận ID mới do server sinh.

`shared_session` nay là false. Response guided có `context_generation` bổ sung;
header `X-Simulation-Generation` hỗ trợ các response ví; đây không phải cookie ID.
Frontend loại checkpoint cũ/khác generation kể cả reset_count trùng sau restart.
Response không cache; khóa riêng không gửi về hoặc lưu vào trình duyệt.
API cookie-less script cần giữ cookie jar giữa các request. Chạy **một Uvicorn
worker**; không có DB/persistence và không hỗ trợ nhiều process dùng chung session.

Handle chữ ký/network/tamper lab thuộc cookie hiện tại. Giới hạn hiện có
(64 khóa, 8 mạng lab, TTL 15 phút) áp dụng riêng trong phiên; lab reset/expiry
chỉ dọn lab đó. Khối & Chuỗi khối vẫn giữ dữ liệu public trên trang, không thêm
Network hay handle server. Không tích hợp Attack Simulator trong thay đổi này.

See [the project review](docs/REVIEW_2026-09-26.md) for confirmed fixes, validation and remaining scope.
The network starts with three validator wallets. Reset Stake keeps their existing keys;
Generate Wallet intentionally creates another identity. Wallets with equal names may still
have different addresses, so selectors display addresses. After updating from the older
wallet-reset implementation, restart Streamlit and refresh the browser for a clean demo.

Credentials & Transactions now lets you submit each saved signed transaction to the network.
Continue in Mining & Consensus Flow, then Verify Credential to verify the included claims.
