# TRUSTMEBRO — Blockchain Profile & Credential Simulation

TRUSTMEBRO is an educational website for exploring how digital credentials are
signed, recorded on a blockchain, synchronized between simulated nodes, verified
and revoked.

The integrated application uses **FastAPI + vanilla HTML/CSS/JavaScript**.
A separate Streamlit learning interface is also retained.

> Educational simulation only. This project does not verify real-world legal
> identity or the factual truth of a credential, connect to a public blockchain,
> or use real cryptocurrency. Use demonstration data, not sensitive personal information.

## Start Here

The integrated application in this README is on branch
`feat/frontend-backend-integration`. Do not assume another branch contains the
same frontend or API features.

### Requirements

- Python — the project has been developed with Python 3.13.
- Node.js with `node` available on PATH — required for JavaScript behavioral tests.
- Python dependencies listed in [requirements.txt](requirements.txt).
- A modern browser. The SHA-256 lab uses Web Crypto; use localhost or HTTPS.

Node.js is needed for tests, not for serving the application. There is no frontend
npm build step and no database setup.

### Install on Windows / PowerShell

```powershell
git clone --branch feat/frontend-backend-integration https://github.com/nhudoannana/TRUSTMEBRO-blockchain.git
cd TRUSTMEBRO-blockchain
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

These commands use the virtual environment directly; PowerShell script execution
policy does not need to be changed.

### Run the Integrated Website

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn api.wallet_api:app --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000** and choose **Bắt đầu mô phỏng**.

| Page | Local URL | Purpose |
| --- | --- | --- |
| Landing | http://127.0.0.1:8000/landing.html | Project introduction |
| Mode selection | http://127.0.0.1:8000/ui/modes.html | Guided journey or independent labs |
| Guided journey | http://127.0.0.1:8000/ui/trustmebro.html | Complete credential lifecycle |
| Lab menu | http://127.0.0.1:8000/ui/modes.html#labs | Choose an experiment |
| Block Explorer | http://127.0.0.1:8000/ui/explorer.html | Read the current browser's guided network |
| Attack lab | http://127.0.0.1:8000/ui/attacks.html | Three isolated attack scenarios |
| API documentation | http://127.0.0.1:8000/docs | FastAPI endpoint documentation |
| API schema | http://127.0.0.1:8000/openapi.json | Inspect the running API contract |

Use **one Uvicorn worker**. Sessions are RAM-only and are not shared between
processes. Do not use `--reload` during a demonstration: restarting the server
clears simulation state. Serve the frontend through FastAPI, not by opening HTML
files directly or deploying only the static pages.

## Two Learning Modes

### Guided Journey — Six Steps

| Step | Action | Result |
| --- | --- | --- |
| 1. Ví & người phát hành | Choose or create an issuer wallet | Signing identity selected |
| 2. Phát hành & ký hồ sơ | Enter demonstration credential data and sign | Signed credential transaction |
| 3. Gửi vào mempool | Submit the signed transaction | Validated transaction queued on the network |
| 4. Tạo block | Choose PoW or PoS | Pending transactions included when block creation succeeds |
| 5. Đồng bộ mạng | Inspect node state and synchronize online peers | Compare chain heights and tip hashes |
| 6. Xác minh & thu hồi | Verify a record or compare a presented document; optionally revoke | Verification details or an on-chain revocation |

Signing, admission, mining, synchronization and verification use the Python
backend. The UI includes objectives, results and next-action guidance.

**Verification distinctions:**

- Verification by credential ID checks the **on-chain record**.
- A presented document is accepted only when the record is `VERIFIED` and
  `presentation_match=true`. A null comparison means no document was compared.
- Revocation requires a signed REVOKE transaction, block inclusion and propagation.
  Submitting the transaction alone does not revoke the on-chain record.
- Step 4 supports PoW and PoS; the guided revocation flow uses explicit PoW mining.

### Independent Labs

Labs are separate experiments, not one shared free-form sandbox. Learning/practice
tabs are available for SHA-256, signatures, Merkle, block/chain, PoW–PoS and synchronization.

| Lab | What users can try | Calculation / state |
| --- | --- | --- |
| SHA-256 | Edit two texts, compare full hashes and changed bits | Browser Web Crypto |
| Chữ ký số | Generate a temporary key, sign and verify messages, test modified text or another key | Backend ECDSA; private key stays server-side |
| Cây Merkle | Enter text leaves, inspect the tree/root and verify a proof | Backend hashes and proofs |
| Khối & Chuỗi khối | Add linked blocks, edit a block and explicitly recompute its evidence | Backend validation; public chain snapshot held on the page |
| PoW–PoS | Compare block creation on separate temporary networks | Actual backend outcomes and measured timings |
| Đồng bộ mạng | Take a node offline, create the sample block, bring it back and synchronize | Retained isolated lab network; scenario-based |
| Sửa dữ liệu | Modify Node-2's sample credential and restore from a valid peer | Retained isolated lab network; scenario-based |
| Tấn công & Phòng vệ | Modify data after signing, impersonate an issuer or replay a transaction | Fresh disposable network for each run |

The integrated Attack lab has **three scenarios**. The separate legacy Streamlit
Attack page is not the same interface and should not be described as six web-lab scenarios.
Replay here means duplicate transaction submission, not a cryptocurrency double-spend.

**Block/chain lab limits and interpretation:**

- Maximum 12 non-genesis blocks; 4,000 text characters per block.
- PoW difficulty 2–5, default 2; at most 200,000 search hashes or three seconds.
- An incomplete search does not add a block. Difficulty 4–5 may hit these bounds.
- Editing preserves recorded evidence. The header hash can remain unchanged while
  the recomputed transaction hash reveals changed content.
- A block can pass its own checks while its preceding chain history is invalid.
- Recomputing hashes does not re-sign, re-mine or repair descendants.
- Reset affects this lab only; reloading the page loses its chain snapshot.

Merkle text leaves are hashed first; parent hashes use concatenated hexadecimal
strings as UTF-8. Odd final hashes are duplicated to form pairs. This example-text
tree is distinct from transaction-ID trees and salted selective-claim trees.

## Block Explorer

Explorer is **read-only** and shows the guided network for the current browser
session. It is not a viewer for the independent lab chains.

Select Node-1/2/3 to inspect blocks, headers and public ISSUE/REVOKE transactions.
Issuer and PoS validator identities are distinct. An offline node can show stale
local data. Use **Làm mới** after mining, synchronization or reset; Explorer does
not automatically poll, mine or synchronize.

## Sessions and Data Lifetime

The integrated FastAPI application isolates simulations using a server-generated
HttpOnly cookie. This is simulation scoping, **not login/authentication**.

| Situation | Behavior |
| --- | --- |
| Tabs with the same browser-profile cookie | Share the guided network and wallets |
| Another profile/browser or separate incognito cookie context | Has a separate simulation |
| Guided reset | Resets only that session's guided state, not other users or independent labs |
| Server restart | Loses all RAM-held simulation state |
| 30 minutes without requests | Session can expire; the next visit receives a fresh context |
| Page reload | Loses page-held lab inputs/results, including the block/chain snapshot |

There are at most **16 live sessions** per server process. When capacity is full,
new sessions receive HTTP 503 rather than evicting an active session. Temporary
signature/network lab handles are session-owned and expire after 15 minutes;
current bounds are 64 signing keys and 8 retained lab networks per session.

Guided responses use a context generation so the frontend can reject stale
checkpoints after reset, expiry or restart. API scripts must retain cookies
between requests. The integrated APIs do not return wallet private keys.

## Architecture and Technologies

| Layer | Implementation |
| --- | --- |
| Integrated frontend | Vanilla HTML, CSS, JavaScript; dark/light themes |
| HTTP API | FastAPI, Pydantic, Uvicorn |
| Cryptography | SHA-256; ECDSA on secp256k1 through `cryptography` |
| Blockchain engine | Transactions, mempools, Merkle trees, blocks, PoW and simulated PoS |
| Network simulation | Three in-process nodes, queues and worker threads |
| State | Browser-scoped server RAM plus page-local lab state |
| Tests | pytest, HTTP/API tests and Node-VM JavaScript behavioral tests |
| Separate learning UI | Streamlit |

Node labels/ports do not mean independently running machines. The integrated
network is an in-process simulation, not a real multi-machine peer-to-peer network.

### Project Layout

| Path | Responsibility |
| --- | --- |
| `api/wallet_api.py` | Integrated API endpoints and static-page entry points |
| `api/session_store.py` | Browser session resolution, capacity and expiry |
| `api/network_store.py`, `api/wallet_store.py` | Guided network/wallet operations |
| `ui/` | Mode selection, journey, labs, Explorer and Attack frontend |
| `blockchain/` | Core cryptography, transactions, chains, nodes, PoS and proofs |
| `tests/` | Core, API, session-isolation and UI tests |
| `app.py`, `state.py`, `pages/` | Separate Streamlit learning interface |
| [AGENTS.md](AGENTS.md) | Contribution/change rules |
| [DEMO_SCRIPT.md](DEMO_SCRIPT.md) | Demo notes; check which interface each section uses |
| [LABS_PHASE1.md](LABS_PHASE1.md) | Detailed lab contracts; some historical sections predate current changes |

### Course Implementation Map

| Item | Topic | Main implementation |
| --- | --- | --- |
| P1 | SHA-256 | `blockchain/hash.py`; SHA-256 lab |
| P2 / P6 | Block structure and header | `blockchain/block.py`; combined block/chain lab and Explorer |
| P3 | Digital signatures | `blockchain/wallet.py`; signature lab and guided issuance |
| P4 | Transactions and mempool | `blockchain/transaction.py`, `blockchain/mempool.py`; guided steps 2–3 |
| P5 | Merkle tree and proof | `blockchain/merkle.py`; Merkle lab and block validation |
| P7 | Proof of Work | `blockchain/mining.py`; block creation and PoW–PoS comparison |
| P8 | Simulated network | `blockchain/node.py`; synchronization and offline/catch-up |
| P9 | Block production and agreement | `blockchain/node.py`, `blockchain/blockchain.py`, `blockchain/pos.py` |
| P10 | Fork / chain split | Node and fork-simulation code; simplified educational handling |
| P11 | Attack demonstrations | Integrated Attack API/UI and separate Streamlit Attack page |

## Tests and Verification

```powershell
.\.venv\Scripts\python.exe -m pytest -q
node --check ui/labs.js
node --check ui/explorer.js
node --check ui/attacks.js
git --no-pager diff --check
```

Node must be available on PATH: UI behavioral tests execute JavaScript through
Node VM. A passing test suite is not a substitute for browser verification.
Test totals change; use the actual result for your checked-out revision rather
than a fixed historical count.

Before a demo, also check the six-step journey, isolated browser sessions,
Merkle proofs, middle-block tampering, disabled-button reasons and Attack outcomes
in the browser. Check both dark/light themes and a narrow viewport.

## Separate Streamlit Interface

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Usually opens at http://localhost:8501. It uses its own application/state handling;
do not assume it shares FastAPI cookie sessions or that its page names and attack
scenarios match the integrated frontend.

## Limitations

- No database or persistence; sessions and keys can be lost on restart/expiry.
- One server process; no distributed deployment or independently secured validators.
- Simplified consensus/fork handling, not a production consensus protocol.
- Mixed-chain scoring uses `16 ** difficulty` per PoW block and 1 per PoS block;
  this is an educational rule, not an equivalent security comparison.
- PoS depends on a trusted server-side validator registry. Full-chain verification
  checks registry signatures but does not replay historical proposer selection.
- Measured PoW/PoS timings are not energy measurements or general performance claims.
- Credential content is plaintext demonstration data. A valid signature proves
  integrity relative to a key, not the truth of the content or legal identity.
- Several network labs intentionally use fixed scenarios rather than unrestricted inputs.
- Some pages load Google Fonts externally; offline presentation should be checked.
- Google login/chatbot are not documented as integrated features of this branch.

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

## Educational Notice

Developed for an academic blockchain course. Demonstrations illustrate real hash,
signature and validation operations within a simplified simulation; they do not
provide production security or real-world credential certification.
