# TRUSTMEBRO — Blockchain & Digital Credential Simulation

**Language: [Tiếng Việt](README.md) | English**

TRUSTMEBRO is an educational website for issuing, signing, recording, verifying and revoking sample credentials on a blockchain. Users can follow a guided journey, run independent experiments, read theory and test their knowledge.

**Main technologies:** Python · FastAPI · HTML/CSS/JavaScript · SHA-256 · ECDSA · RSA · simulated PoW/PoS.

> Educational simulation only. The system does not verify real-world identity or the legal validity of credentials, connect to a public blockchain, or use real cryptocurrency. Use demonstration data only.

## Contents

- [Installation and startup](#installation-and-startup)
- [Using the website](#using-the-website)
- [Independent labs](#independent-labs)
- [AI chatbot](#ai-chatbot)
- [Architecture and source code](#architecture-and-source-code)
- [Sessions and data](#sessions-and-data)
- [Verification](#verification)
- [Deployment](#deployment)
- [Limitations](#limitations)

## Installation and startup

### Requirements

- Python; the project was developed with Python 3.13.
- A modern browser, using localhost or HTTPS for Web Crypto.
- Node.js on PATH when running JavaScript behavioral tests. No npm build is required to serve the website.
- No database setup: simulation state is stored in RAM.

### Windows / PowerShell

```powershell
git clone --branch main https://github.com/nhudoannana/TRUSTMEBRO-blockchain.git
cd TRUSTMEBRO-blockchain
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn api.wallet_api:app --host 127.0.0.1 --port 8000
```

These commands use the virtual environment's Python directly, without changing PowerShell execution policy.

### macOS / Linux

```bash
git clone --branch main https://github.com/nhudoannana/TRUSTMEBRO-blockchain.git
cd TRUSTMEBRO-blockchain
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m uvicorn api.wallet_api:app --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000**. Run from the repository root with **one worker**. Avoid `--reload` during a demonstration that needs to preserve state. Serve the frontend through FastAPI; opening HTML files directly or hosting only static pages does not provide the simulation backend.

| Page | Path on the same server | Purpose |
|---|---|---|
| Home | `/landing.html` | Product introduction |
| Mode selection | `/ui/modes.html` | Choose a learning path |
| Theory | `/ui/theory.html` | Reading and practice links |
| Guided journey | `/ui/trustmebro.html` | Six-step credential lifecycle |
| Lab menu | `/ui/modes.html#labs` | Independent experiments |
| Block Explorer | `/ui/explorer.html` | Read the guided network |
| Attacks | `/ui/attacks.html` | Three defense-check scenarios |
| Quiz | `/ui/quiz.html` | Practice and mixed test |
| API docs | `/api/docs` | Swagger UI |
| API schema | `/openapi.json` | API contract |
| Health check | `/api/health` | Process liveness |

## Using the website

From the home page, choose **Bắt đầu mô phỏng** (Start simulation), then Theory, Guided journey, Labs or Quiz. The interface includes light/dark and VI/EN controls; translation coverage varies by page.

### Guided journey — six steps

| Step | Action | What to observe |
|---|---|---|
| 1. Wallet and issuer | Select or create an issuer wallet | The key identity used for signing |
| 2. Issue and sign | Enter sample data and sign | Credential content and its signature |
| 3. Submit to mempool | Submit the signed transaction | Validation and pending admission |
| 4. Create a block | Choose PoW or PoS and create a block | Nonce/validator and inclusion result |
| 5. Synchronize | Inspect nodes, toggle availability and synchronize | Height, tip hash and lagging copies |
| 6. Verify and revoke | Verify, compare a document or revoke | On-chain status and validation layers |

- Verification by credential ID checks the on-chain record. Accepting a presented document requires `VERIFIED` and `presentation_match=true`; null means no document was compared.
- A pending REVOKE does not revoke a confirmed credential. It must be included in a block and propagated to the node being checked. The guided revocation flow uses PoW.
- A valid signature establishes consistency between content and a key, not the real-world truth of the content.

### Block Explorer

Choose Node-1/2/3 to inspect blocks, headers and ISSUE/REVOKE transactions in the **current guided session**. Explorer does not show independent lab chains, mine or synchronize. Refresh after operations; offline nodes may retain stale copies. Issuers and PoS validators have distinct roles.

### Quiz

The current interface contains **400 questions, 13 topics and three difficulty levels**. Practice by topic or take a **40-question mixed test in 60 minutes**, with a 70% self-assessment pass threshold. Review results and answers after submission. Practice progress is stored locally in the browser.

Question count does not establish that all content has been reviewed. The repository retains an earlier reviewed 36-question subset in `ui/quiz_questions.json`, distinct from the current 400-question interface. Quiz topics such as Bitcoin, UTXO, Ethereum, DeFi and attacks do not mean those systems are implemented as simulations.

## Independent labs

Each lab is a separate experiment, rather than a shared sandbox network. Use the learning/practice tabs, enter sample data, perform an action and read the result and validation reasons. Use the lab's own reset control to repeat an experiment.

| Lab | Path | Experiment |
|---|---|---|
| SHA-256 | `/ui/labs.html#sha` | Compare texts, hashes and changed output bits |
| RSA-OAEP | `/ui/labs.html#rsa-oaep` | Encrypt/decrypt; compare keys and ciphertexts |
| RSA-PSS | `/ui/labs.html#rsa-pss` | Sign/verify; change a message or key |
| ECDSA signatures | `/ui/labs.html#signatures` | Create a temporary key, sign and tamper |
| Merkle Tree | `/ui/labs.html#merkle` | Build trees, edit leaves and verify inclusion |
| Blocks and chain | `/ui/labs.html#blocks` | Add blocks, inspect headers and edit a middle block |
| PoW–PoS | `/ui/labs.html#consensus` | Compare block production on separate networks |
| Synchronization | `/ui/labs.html#network` | Take a node offline, create a block and sync; queue/HTTP |
| Fork and Reorg | `/ui/labs.html#fork` | Control delivery, partitions and competing branches |
| Tampering | `/ui/labs.html#tamper` | Modify Node-2 and recover from a valid peer |
| Attacks and defenses | `/ui/attacks.html` | Tamper after signing, impersonate an issuer and replay |

### Interpreting results

- **Merkle:** a proof matching an expected root establishes inclusion under that encoding; it does not establish a trustworthy root, valid signatures or true content. The text lab hashes UTF-8 leaves, hashes concatenated hexadecimal child hashes for parents and duplicates the final hash at odd levels. Text trees differ from TxID and selective-claim trees.
- **RSA:** RSA-2048; OAEP uses SHA-256 with at most 190 UTF-8 plaintext bytes. PSS uses SHA-256 and a 32-byte salt. The backend handles plaintext and private keys, so this is not E2EE.
- **Blocks/chain:** at most 12 non-genesis blocks, 4,000 characters per block and difficulty 2–5. Nonce search is bounded by 200,000 hashes or three seconds; unsuccessful searches add no block. Editing retains old evidence to expose inconsistency. Recomputing hashes does not re-sign, re-mine or repair descendants.
- **Fork:** choose a valid branch with greater cumulative work; each non-genesis PoW block contributes `16^difficulty`. On equal work, a node retains its current valid branch, so nodes may temporarily have different tips. Known blocks outside the selected branch are stale; blocks with missing parents are orphan blocks.
- **Credential reorg:** C1 detaches REVOKE but retains ISSUE → ACTIVE, with a valid REVOKE potentially restored to pending. C2 detaches both → no confirmed credential; ISSUE may be pending but REVOKE lacks a confirmed ISSUE. C3 retains the same REVOKE TxID on the winning branch → still REVOKED, without restoring that transaction to the pool.
- **Attacks:** replay means duplicate transaction submission, not currency double-spending. 51%, Sybil/Eclipse and Timejacking are theory topics, not scenarios in the current attack engine.

## AI chatbot

The widget explains concepts and suggests labs. It **cannot read wallet, node, credential, lab or Quiz progress**, and has no tools to act for users. Responses can be incorrect; compare them with theory and actual validation results.

The chatbot is disabled by default. The website and labs remain usable without the SDK or API key.

1. Install the optional dependency in an isolated environment:
   ```bash
   python -m pip install -r requirements.txt -r requirements-chatbot.txt
   ```
2. Configure server-side environment variables:

   | Variable | Value / purpose |
   |---|---|
   | `CHATBOT_ENABLED` | `1` to enable; defaults to `0` |
   | `GEMINI_API_KEY` | Server-side key; never put it in frontend code or commits |
   | `GEMINI_MODEL` | Optional; the adapter currently accepts only its default, `gemini-3.5-flash-lite` |

3. Restart the server to apply configuration. Check `/api/chatbot/status`, open the widget, acknowledge the data-sending notice and ask a concept question.

`requirements-chatbot.txt` pins `google-genai==2.29.0` and notes Pydantic ≥2.12.5. Installing the SDK may change base dependencies; verify regressions in the deployment environment. Configured status and mocked tests do not establish live Gemini availability.

Questions/history are sent to the provider when using AI. Do not enter keys, cookies, personal information or secrets. The backend bounds inputs, history, quota and concurrency and does not automatically retry. The request deadline is 20 seconds.

| Symptom | Check |
|---|---|
| Disabled or missing configuration | Status endpoint, environment variables and SDK |
| `provider_timeout` | Timing and server logs |
| `provider_unavailable` / HTTP 502 | Find `chatbot_diagnostic`; inspect stage, exception class and numeric upstream status |
| Rate-limited or busy session | Wait as instructed before a new action |

Diagnostic logs omit prompts, history, keys, cookies, raw provider bodies and exception strings. Diagnostics support investigation; they do not fix every provider failure. HTTP 502 alone does not establish an invalid key or exhausted quota.

## Architecture and source code

The browser calls same-origin APIs. FastAPI resolves the session and dispatches operations to wallet/network/lab services and the blockchain engine; simulation state resides in RAM. The optional chatbot calls Gemini without lab-state access. Quiz progress stays in browser storage.

| Component | Location / responsibility |
|---|---|
| API and static entry | `api/wallet_api.py` |
| Sessions, wallets and guided network | `api/session_store.py`, `api/wallet_store.py`, `api/network_store.py` |
| RSA / Fork / HTTP labs | `api/rsa_lab.py`, `api/fork_lab.py`, `api/http_network.py` |
| Chatbot | `api/chatbot_api.py`, `docs/CHATBOT_CONTEXT_V1.md`, `ui/chatbot.js` |
| Blockchain core | `blockchain/`: hash, wallets, transactions, mempools, Merkle, blocks, mining, PoS, nodes and forks |
| Website | `landing.html`, `ui/`: pages, navbar, theme and translations |
| Tests | `tests/`: core, API, sessions, labs and JavaScript behavior |
| Separate Streamlit UI | `app.py`, `state.py`, `pages/` |
| Contribution rules | [AGENTS.md](AGENTS.md) |
| Demo/lab documentation | [DEMO_SCRIPT.md](DEMO_SCRIPT.md), [LABS_PHASE1.md](LABS_PHASE1.md); some sections are historical |

Cryptography uses `cryptography`: SHA-256, secp256k1 ECDSA and RSA. The main network consists of three in-process nodes. HTTP labs use listeners/sockets for simulation; this does not establish a complete, independent multi-machine network.

### Course implementation map

| Item | Topic | Main source |
|---|---|---|
| P1 | SHA-256 | `blockchain/hash.py` |
| P2 / P6 | Block and header | `blockchain/block.py` |
| P3 | Digital signatures | `blockchain/wallet.py`; additional RSA labs |
| P4 | Transactions and mempool | `blockchain/transaction.py`, `blockchain/mempool.py` |
| P5 | Merkle tree/proofs | `blockchain/merkle.py`, `blockchain/claim_merkle.py` |
| P7 | PoW | `blockchain/mining.py` |
| P8 | Simulated networking | `blockchain/node.py`, `blockchain/net_node.py` |
| P9 | Block production/consensus | `blockchain/blockchain.py`, `blockchain/pos.py` |
| P10 | Fork/reorg | `blockchain/fork_simulator.py`, `blockchain/fork_transport.py`, `api/fork_lab.py` |
| P11 | Attack checks | Integrated Attack API/UI and separate Streamlit page |

## Sessions and data

A server-generated HttpOnly cookie scopes simulation state; **it is not login**. Tabs with the same cookie share guided wallets/network. Other browsers or profiles have separate sessions.

- Guided reset affects that session's guided state; labs have separate data/reset controls.
- Restarting the server loses RAM state and temporary keys. Sessions may expire after 30 minutes without requests.
- At most 16 live sessions per process; new sessions receive 503 when full instead of evicting active users.
- Reload loses page-held data, such as block/chain snapshots. Quiz localStorage has a separate lifetime.
- API scripts must retain cookies between requests. Integrated APIs do not return wallet private keys.
- There is no database, shared worker state or server-side score account.

## Verification

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

On Windows, use `.\.venv\Scripts\python.exe` if the environment is not activated. Node.js must be on PATH for UI behavioral tests. Scoping collection to `tests` avoids collecting archived evidence tests elsewhere. Historical test totals are not results for the current revision.

Before a demonstration, check the six-step journey, isolated sessions, valid/invalid Merkle proofs, RSA, middle-block tampering, fork/reorg, attacks, Quiz, light/dark themes and narrow screens in a browser. Automated provider tests use mocks; live Gemini checks are separate and may consume quota.

### Separate Streamlit interface

```bash
python -m streamlit run app.py
```

Usually opens at http://localhost:8501. It has separate state and pages; do not assume shared FastAPI sessions or matching Attack scenarios.

## Deployment

For a Python service such as Render, use the repository root:

| Setting | Value |
|---|---|
| Build without AI | `pip install -r requirements.txt` |
| Build with AI | `pip install -r requirements.txt -r requirements-chatbot.txt` |
| Start | `uvicorn api.wallet_api:app --host 0.0.0.0 --port $PORT --workers 1` |
| Health path | `/api/health` |

Set chatbot variables in the server environment, not the repository. Deploy the intended revision and check health, existing labs and chatbot status. A successful answer verifies the provider only at that time. Restart/redeploy clears simulation RAM. Static Netlify hosting alone does not replace the Python API service.

## Limitations

- Consensus/networking are educational, without production security or availability guarantees.
- PoW scores of `16^difficulty` and PoS scores of `1` per block are educational rules, not equivalent security measures.
- PoS relies on a trusted validator registry; chain validation does not fully replay historical proposer selection.
- Lab timings are not energy measurements or general performance conclusions.
- HTTP/NetNode exists but retains credential-reconciliation and invalid-chain recovery limitations. Passing queue checks does not establish repaired HTTP behavior.
- Some labs use fixed scenarios. No currency UTXO/double-spending or 51% attack engine is implemented.
- Sample credentials are plaintext. RSA labs do not encrypt the entire blockchain or establish E2EE.
- Chatbot availability depends on the provider and may fail with timeouts/502. Its context still describes the earlier 36-question Quiz while the current interface has 400; cross-check Quiz scope.
- External fonts/videos and AI require connectivity; check before offline presentations.
- Simulation cookies are not user accounts or an integrated Google Login system.

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



## Academic notice

Developed for a blockchain course. Hashing, signing and validation run as real operations within a simplified model; simulation results do not provide legal certification or real-world security guarantees.
