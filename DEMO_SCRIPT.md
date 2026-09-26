# TRUSTMEBRO — Video Demonstration Script

**Target duration:** 5–8 minutes
**Objective:** Demonstrate one complete end-to-end credential flow and at least two tamper/attack cases that the system detects and rejects.

---

## 1. Preparation Before Recording

Complete this checklist before starting the screen recording:

- [ ] Activate the virtual environment: `.venv\Scripts\activate`
- [ ] Install dependencies: `pip install -r requirements.txt`
- [ ] Run all tests and confirm 51 pass: `python -m pytest -v`
- [ ] Start Streamlit: `streamlit run app.py`
- [ ] Confirm the Dashboard loads at `http://localhost:8501` with all metrics at zero or default
- [ ] If the blockchain already contains data from a previous session, restart Streamlit to reset
- [ ] Prepare sample credential information (e.g., Issuer: "Demo University", Holder: "Alice", Title: "BSc Computer Science", Credential ID: "CRED-0001")
- [ ] Confirm that no real private keys, passwords, or sensitive personal information will appear in the recording
- [ ] Close unrelated browser tabs and notifications

---

## 2. Timed Demonstration Script

### 00:00–00:30 — Problem Introduction and System Architecture

**Screen:** Dashboard (home page)

**Actions:**
1. Show the Dashboard title "TRUSTMEBRO" and the overview text.
2. Scroll to the **End-to-End Flow** diagram.
3. Briefly point to the sidebar showing all 12 pages.

**Narration:**
> "TRUSTMEBRO is a blockchain simulation that demonstrates how digital credentials — such as university degrees — can be issued, verified, and protected from tampering. The system covers the full blockchain pipeline: from SHA-256 hashing and digital signatures, through transaction validation and mining, to multi-node consensus and credential verification. Let me walk you through a complete flow."

**Expected result:** Dashboard displays metrics (all at 0 initially), the flow diagram is visible, and the sidebar lists all 12 pages.

---

### 00:30–01:15 — SHA-256 and Avalanche Effect

**Screen:** SHA-256 (page `1_Hash_Demo.py`)

**Actions:**
1. Navigate to **SHA-256** in the sidebar.
2. Type `"Hello"` in the input field and click **Generate Hash**.
3. Point out that the output is always 64 hex characters (256 bits).
4. Scroll to **Avalanche Effect**: enter `"Hello"` and `"hello"` (lowercase h). Click to compare.
5. Show the bit difference percentage (expected: ~45–55%).

**Narration:**
> "SHA-256 always produces a fixed-length 256-bit hash. Even changing a single character — from uppercase H to lowercase h — changes roughly 50% of the bits. This is called the Avalanche Effect, and it makes it impossible to predict how the hash will change."

**Expected result:** Hash displayed (64 characters), bit difference around 50%.

---

### 01:15–02:00 — Wallet Creation, Signing, and Verification

**Screen:** Wallet & Digital Signature (page `2_Wallet.py`)

**Actions:**
1. Navigate to **Wallet & Digital Signature**.
2. Enter name `"Demo University"` and click **Generate Wallet**.
3. Show the public key and address. Point out that the private key is hidden by default.
4. Type a message, e.g., `"Transfer 10 BTC to Bob"`, click **Sign**.
5. Click **Verify** → result: ✅ VALID.
6. Change the message to `"Transfer 100 BTC to Bob"` (keeping the same signature) → click **Verify** → result: ❌ INVALID.

**Narration:**
> "We create a wallet using ECDSA with the SECP256K1 curve — the same algorithm used by Bitcoin. The private key signs messages; the public key verifies them. Watch what happens when I modify the message after signing: the signature becomes invalid. This proves the signer's identity and that the content has not been altered."

**Expected result:** Signature valid for original message, invalid after modification.

---

### 02:00–02:45 — Credential Transaction Creation

**Screen:** Mining & Consensus Flow (page `9_Mining_Flow.py`)

**Actions:**
1. Navigate to **Mining & Consensus Flow**.
2. If no wallet exists, click **⚡ Tạo wallet demo** to create one quickly.
3. In section **① Tạo & Gửi Transaction**:
   - Select the Issuer wallet (e.g., "Demo University" or "Demo Issuer").
   - Set Credential ID: `CRED-0001`.
   - Set Holder: `Alice`.
   - Set Title: `BSc Computer Science`.
   - Select target node: `Node-1`.
4. Click **📤 Create → Sign → Submit → Broadcast**.

**Narration:**
> "Now I create a credential and package it into a transaction. The system signs it with the Issuer's private key, computes its hash as the transaction ID, then submits it to Node-1. Node-1 validates the signature and ledger status, adds it to its mempool, and broadcasts it to the other two nodes."

**Expected result:** Success message, mempool count shows 1 TX on each online node.

---

### 02:45–03:30 — Transaction Broadcast and Three-Node Mempool

**Screen:** Network (page `8_Network.py`)

**Actions:**
1. Navigate to **Network**.
2. Show the status table: three nodes, all ONLINE, Height 0, Mempool 1.
3. Expand one node's detail to show the pending transaction (tx_id, type, credential_id).

**Narration:**
> "All three nodes now hold the same transaction in their independent mempools. Each node validated the transaction independently — no node trusts another. This is the foundation of decentralization."

**Expected result:** Status table shows 3 nodes ONLINE with 1 pending TX each.

---

### 03:30–04:30 — Mining, Merkle Root, Proof of Work, and Block Creation

**Screen:** Mining & Consensus Flow (page `9_Mining_Flow.py`)

**Actions:**
1. Return to **Mining & Consensus Flow**.
2. In section **② Mine**:
   - Select miner: `Node-1`.
   - Set difficulty: `3`.
   - Note: "TX chờ trong Mempool" shows 1.
3. Click **⛏️ Mine Block**.
4. Show the mining result: nonce, number of attempts, time, block hash.
5. Point out that the hash starts with three zeros (matching difficulty 3).

**Narration:**
> "The miner takes transactions from its mempool, computes a Merkle Root, and then searches for a nonce that produces a block hash starting with three zeros — this is Proof of Work. It took [X] attempts and [Y] seconds. The computational cost makes it prohibitively expensive to alter historical blocks."

**Expected result:** Block mined, hash starts with `000`, attempts and time displayed.

---

### 04:30–05:15 — Block Broadcast and Node Consensus

**Screen:** Mining & Consensus Flow (page `9_Mining_Flow.py`) — results table

**Actions:**
1. After mining, show the **results table** beneath the mine button.
2. Point out that all three nodes now show:
   - Same Height (1).
   - Same Tip hash.
   - Mempool: 0 (transaction removed after mining).
3. Highlight the consensus message: "🤝 CONSENSUS REACHED".

**Narration:**
> "After Node-1 mined the block, it broadcast the block to Nodes 2 and 3. Each peer independently validated the block — checking the previous hash, Merkle Root, Proof of Work, and every transaction signature. All three nodes now agree on the same chain. This is consensus."

**Expected result:** All 3 nodes at Height 1, same tip hash, 0 pending TX. Consensus message displayed.

---

### 05:15–06:00 — Credential Verification

**Screen:** Verify Credential (page `10_Verify.py`)

**Actions:**
1. Navigate to **Verify Credential**.
2. Enter Credential ID: `CRED-0001`.
3. Click **🔍 Verify**.
4. Walk through the 12 verification steps, pointing to each ✅.
5. Show the credential information: Issuer, Holder, Title, Block Height, TX hash.
6. Highlight the final result: **✅ VERIFIED — Credential hợp lệ và đang ACTIVE**.

**Narration:**
> "A Verifier enters only the Credential ID. The system checks twelve aspects: that the credential exists, the transaction hash is correct, the Issuer's signature is valid, the Merkle Proof matches the block's root, the Proof of Work is valid, and the entire blockchain is intact. All twelve checks pass — the credential is verified and active."

**Expected result:** 12/12 steps pass, final status VERIFIED, credential info displayed.

---

### 06:00–07:15 — Attack Simulator

**Screen:** Attack Simulator (page `11_Attacks.py`)

**Actions:** Demonstrate at least **Attack 1** and **Attack 3** (or Attack 6). See required attack details in Section 3 below.

#### Attack A — Tamper with a Transaction After Signing (Attack 1)

1. Click **▶️ Chạy Attack 1**.
2. Walk through the results table:
   - Row 1: TX created with "IELTS 6.5" — ✅ valid.
   - Row 2: `verify_transaction` before tamper — ✅ PASS.
   - Row 3: Payload modified to "IELTS 8.5" — 🔴 tampered.
   - Row 4: `tx_id` no longer matches `compute_hash()` — ❌ different.
   - Row 5: `verify_transaction` after tamper — ❌ INVALID.
3. Read the conclusion: "Bảo vệ bởi: Chữ ký số (ECDSA)".

**Narration:**
> "Attack 1: an attacker modifies a credential — changing IELTS 6.5 to 8.5 — after it was signed. The transaction hash changes, but the original signature does not match the new hash. The system rejects it immediately. This is the digital signature layer of protection."

#### Attack B — Swap a Transaction in a Block (Attack 3)

1. Click **▶️ Chạy Attack 3**.
2. Walk through the results table:
   - Original TX in Block 1 — ✅.
   - Replaced with a fake TX — 🔴 tampered.
   - Merkle Root in the block header remains unchanged.
   - Merkle Root recalculated from the new TX — ❌ different from header.
   - `is_chain_valid()` — ❌ DETECTED.
3. Read the conclusion: "Bảo vệ bởi: Merkle Tree".

**Narration:**
> "Attack 3: an attacker replaces an entire transaction inside a mined block. Even though the new transaction has a valid signature, the Merkle Root computed from the modified transactions no longer matches the root stored in the block header. The blockchain validation catches this immediately."

#### Optional: Attack 6 — Recompute All Hashes

If time permits, also demonstrate Attack 6 to show that recalculating hashes is not enough when Proof of Work is required:

1. Click **▶️ Chạy Attack 6**.
2. Show that PoW fails after recomputing.
3. Show the re-mining cost estimate table.

---

### 07:15–07:45 — Conclusion and Limitations

**Screen:** Dashboard or Attack Simulator summary expander

**Actions:**
1. Open the **📋 Tổng kết: 6 lớp bảo vệ** expander on the Attack Simulator page.
2. Show the summary table of six protection layers.
3. Return to the Dashboard; point to the updated metrics (Blocks, TXs, Active Credentials).

**Narration:**
> "TRUSTMEBRO demonstrates six layers of protection: digital signatures, hash chain linkage, Merkle Trees, issuer registry, replay detection, and Proof of Work. Each layer is independent — an attacker would need to defeat all of them simultaneously. This is an educational simulation: all data is in memory, the network uses in-process queues rather than real sockets, and consensus is simplified. But the core mechanisms are the same ones used by real blockchains like Bitcoin and Ethereum. Thank you for watching."

**Expected result:** Summary table visible, Dashboard shows non-zero metrics reflecting the demo activity.

---

## 3. Required Attack Demonstrations

### Attack A — Tamper with a Transaction After Signing

| Step | Page / Control | Expected Output |
|---|---|---|
| Open Attack Simulator | Sidebar → **Attack Simulator** | Page loads with demo blockchain info |
| Click **▶️ Chạy Attack 1** | Attack 1 section | Results table appears |
| Row 3: Payload modified | "IELTS 6.5" → "IELTS 8.5" | 🔴 Giả mạo |
| Row 4: Hash comparison | `tx_id` ≠ `compute_hash()` | ❌ KHÁC |
| Row 5: Signature check | `verify_transaction` after tamper | ❌ INVALID |
| Conclusion | Red box | "Bảo vệ bởi: Chữ ký số (ECDSA)" |

**Key point:** The original signature was computed over the original hash. Changing the payload produces a different hash, so the signature no longer matches.

### Attack B — Swap a Transaction in a Block (Merkle Detection)

| Step | Page / Control | Expected Output |
|---|---|---|
| Click **▶️ Chạy Attack 3** | Attack 3 section | Results table appears |
| Row 2: Fake TX inserted | New tx_id shown | 🔴 Giả mạo |
| Row 3: Header Merkle Root | Original root preserved | Giữ nguyên |
| Row 4: Recalculated Root | Different from header | ❌ KHÁC |
| Row 5: Chain validation | `is_chain_valid()` | ❌ DETECTED |
| Conclusion | Red box | "Bảo vệ bởi: Merkle Tree" |

**Key point:** The Merkle Root in the block header acts as a fingerprint of all transactions. Any substitution is detected without needing to recheck every transaction.

### Optional: Replay Attack (Attack 5a)

| Step | Page / Control | Expected Output |
|---|---|---|
| Click **▶️ Chạy Attack 5** | Attack 5 section | Two sub-tables appear |
| 5a: Submit TX first time | Same tx_id | ✅ ACCEPT |
| 5a: Submit TX second time | Same tx_id (replay) | ❌ REJECTED |

---

## 4. Final Submission Checklist

- [ ] All 51 tests pass: `python -m pytest -v`
- [ ] Streamlit starts without errors: `streamlit run app.py`
- [ ] Dashboard loads correctly with all metrics at default values
- [ ] All three nodes display correctly on the Network page
- [ ] A valid transaction moves from the mempool into a mined block
- [ ] Accepted transactions are removed from the mempool after mining
- [ ] All three nodes reach the same chain height and tip hash after mining (consensus)
- [ ] Credential verification returns VERIFIED for the demonstrated Credential ID
- [ ] The Attack Simulator detects modified data in all six scenarios
- [ ] README installation instructions have been manually verified on a clean environment
- [ ] No real private keys or sensitive personal data are committed to the repository
- [ ] Git does not track `__pycache__/`, `*.pyc`, `.pytest_cache/`, `.venv/`, or other generated files (verify with `.gitignore`)
- [ ] All screenshots use safe demonstration data with no real personal information

---

## 5. Defense Questions and Short Answers: P1–P11

### P1 — SHA-256

**Why does SHA-256 always produce 256 bits?**
SHA-256 uses a fixed compression function that processes any input through padding and block iteration, always producing a 256-bit (32-byte, 64 hex character) digest. The output length is independent of input length.

**How is hashing different from encryption?**
Hashing is one-way: you cannot recover the original input from a hash. Encryption is two-way: with the correct key, the ciphertext can be decrypted back to the plaintext. SHA-256 has no key and no decryption operation.

**What is the Avalanche Effect?**
A minimal change to the input (even one bit) causes roughly 50% of the output bits to change. In our implementation, `bit_difference_percent()` compares two hashes and reports this percentage.

---

### P2 — Block Structure

**How does `previous_hash` reveal tampering?**
Each block stores the SHA-256 hash of the preceding block's header in its `previous_hash` field. If an attacker modifies any header field in block *N*, its `compute_hash()` output changes, and block *N+1*'s stored `previous_hash` no longer matches. `Blockchain.is_chain_valid()` detects this mismatch.

**Why does changing one block affect every following block?**
Because each block's hash depends on its header (which includes `previous_hash`), modifying block *N* changes its hash, which invalidates block *N+1*'s `previous_hash`, which changes block *N+1*'s hash, and so on — a cascade through the entire chain.

> *Owner review required: the assigned member must verify this answer against the final code before submission.*

---

### P3 — ECDSA Digital Signature

**What are the roles of the private and public keys?**
The private key signs data (only the owner possesses it). The public key verifies signatures (anyone can hold it). In our `Wallet` dataclass, `private_key_pem` is used by `sign_message()` and `public_key_hex` is used by `verify_signature()`.

**What does a digital signature prove?**
It proves (1) **authenticity** — the signer possesses the corresponding private key, and (2) **integrity** — the signed content has not been modified.

**Does it hide the signed content?**
No. The message payload is transmitted in plaintext. A signature is not encryption.

---

### P4 — Transaction Validation and Mempool

**What does a node validate before accepting a transaction?**
`Mempool.add_transaction()` performs five checks in order:
1. Transaction format and signature via `verify_transaction()`.
2. No duplicate `tx_id` in the mempool (anti-replay).
3. Issuer public key is in the authorized issuer registry (if configured).
4. For ISSUE: credential not already ACTIVE in the ledger. For REVOKE: credential is ACTIVE and was issued by the same Issuer.

**How is replay detected?**
The mempool maintains a set of `tx_id` values. Submitting the same transaction twice produces the same `tx_id`, which is rejected at step 2.

---

### P5 — Merkle Tree and Merkle Proof

**What is the purpose of the Merkle Root?**
The Merkle Root is a single hash that represents all transactions in a block. It is stored in the `BlockHeader.merkle_root` field. If any transaction changes, the root changes, so the block header acts as a compact fingerprint of the entire transaction set.

**Why does a Merkle Proof require O(log n) hashes?**
A Merkle Tree is a binary tree. To prove that a leaf belongs to a root, you only need the sibling hash at each level of the tree. With *n* leaves, the tree has ⌈log₂ n⌉ levels, so the proof contains at most ⌈log₂ n⌉ hashes — far fewer than the *n* transactions.

---

### P6 — Block Header

**Which fields are in this project's block header?**
The `BlockHeader` dataclass contains six fields: `version`, `previous_hash`, `merkle_root`, `timestamp`, `difficulty`, `nonce`.

**What roles do the Merkle Root and transaction count play?**
The `merkle_root` ensures transaction integrity without storing all transactions in the header. The `transaction_count` (stored in `Block`, not the header) provides a quick summary; `is_chain_valid()` uses the Merkle Root for actual verification.

> *Owner review required: the assigned member must verify this answer against the final code before submission.*

---

### P7 — Proof of Work

**What are nonce and difficulty?**
The `nonce` is an integer incremented from 0 until `compute_hash()` produces a hash starting with `difficulty` zeros. In `mine_block()`, the function loops `nonce = 0, 1, 2, …` until the condition is met.

**Why does mining time rise rapidly with difficulty?**
Each additional leading zero requires approximately 16× more attempts on average (one more hex digit). Difficulty 2 averages ~256 attempts; difficulty 4 averages ~65,536.

**How does Proof of Work make historical tampering expensive?**
An attacker who modifies a block must re-mine that block and every subsequent block to restore valid hashes — all while the honest network continues mining ahead. The cumulative computational cost makes this impractical.

> *Owner review required: the assigned member must verify this answer against the final code before submission.*

---

### P8 — P2P Network

**What does each full node store?**
Each `Node` instance holds its own `Blockchain` (independent chain copy), `Mempool` (pending transactions), `inbox` (message queue), and a daemon worker thread. The `Network` class manages routing and a thread-safe event log.

**Why must every node validate independently?**
Blockchain is trustless: no node should rely on another node's validation result. Each node runs `verify_transaction()`, checks Merkle Roots, verifies Proof of Work, and validates `previous_hash` linkage independently before accepting a block.

---

### P9 — Mining and Consensus

**Explain the flow: Mempool → Mining → Broadcast → Consensus.**
1. `Node.mine_pending()` takes up to *N* transactions from the mempool.
2. A `Block` is created with a `Merkle Root` computed from the transaction hashes.
3. `mine_block()` finds a nonce satisfying the difficulty target (Proof of Work).
4. The mined block is added to the miner's chain, and the included transactions are removed from the miner's mempool.
5. The block is broadcast to all online peers via `Network.broadcast()`.
6. Each peer's `_handle_block()` validates the block (previous_hash, Merkle Root, PoW, each TX signature and ledger status). Valid blocks are accepted; invalid blocks are rejected with a logged reason.

**Why must accepted transactions be removed from the mempool?**
If mined transactions remained in the mempool, a future miner could include them again, creating duplicate entries. `Mempool.remove_transactions()` deletes all transaction IDs that were included in the accepted block.

---

### P10 — Fork / Chain Split

**When does a fork occur?**
A fork occurs when two miners produce valid blocks at approximately the same time, each extending the same tip. Different nodes may receive different blocks first, temporarily holding divergent chains.

**At what level does this project handle forks?**
The project implements **detection and longest-chain sync**, not full fork resolution. In `_handle_block()`, if a received block's `previous_hash` does not match the node's current tip, the node logs `"STALE/FORK detected"` and calls `request_sync()`. The `_handle_sync_response()` method replaces the local chain with the peer's chain only if the peer's chain is longer and passes `is_chain_valid()`. There is no competing-chain comparison at equal heights, no orphan block storage, and no chain reorganization.

---

### P11 — Attack Simulator

**What does the Attack Simulator demonstrate?**
Six attack scenarios, each running on a `copy.deepcopy()` of the blockchain to avoid affecting real data:

| # | Attack | Protection Layer |
|---|---|---|
| 1 | Modify credential after signing | ECDSA digital signature |
| 2 | Modify block header data | Hash chain linkage |
| 3 | Replace a transaction in a block | Merkle Tree root mismatch |
| 4 | Fake Issuer (unauthorized wallet) | Issuer registry |
| 5 | Replay TX / Duplicate credential ID | Mempool duplicate check + ledger status |
| 6 | Recompute all hashes after tampering | Proof of Work |

**Why does editing a signed transaction invalidate its signature?**
The `tx_id` (transaction hash) is computed from the canonical JSON of the transaction payload. The signature signs this `tx_id`. Modifying the payload changes the `compute_hash()` output, so the stored `tx_id` and signature no longer correspond to the new content.

**Why is recalculating a hash insufficient if Proof of Work is not mined again?**
Recalculating the hash is trivial (one SHA-256 call), but Proof of Work requires finding a nonce that makes the hash start with `difficulty` zeros. This takes thousands to millions of attempts. Without re-mining, the block's hash will not satisfy the difficulty target, and `is_valid_pow()` returns `False`.
