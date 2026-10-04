# TRUSTMEBRO Labs — phase 1

Run the existing single-process app:

```text
python -m uvicorn api.wallet_api:app --host 127.0.0.1 --port 8000
```

Home: http://127.0.0.1:8000/ui/modes.html#labs

Exercises: `/ui/labs.html#sha`, `#signatures`, `#merkle`, `#blocks`, `#consensus`, `#network`, `#tamper`.
The guided PoW/PoS journey remains `/ui/trustmebro.html`. All pages use
the saved `trustmebro-theme` preference. `/ui/explorer.html` is a separate read-only
view of the shared guided network, not another isolated lab.

## Where calculations run

The product has two modes: the existing six-step guided credential journey
and independent experiments. There is no third mode or shared lab sandbox.
Lab order: SHA-256, signatures, Merkle, Khối & Chuỗi khối,
PoW–PoS, network synchronization, tamper detection. Explorer remains a
read-only guided-journey tool, not a lab data source.

Existing scope limits are unchanged: signatures/Hash/Merkle allow repeated
editable inputs; PoW–PoS accepts editable credential metadata and conditions
but uses fresh networks and fixed default difficulty. Network-sync retains
one fixed sample credential/block per initialization, and tamper detection
edits only the fixed Node-2 title. These two scenario labs have not been
expanded into free-form blockchain experiments in this change.

- **SHA-256:** browser Web Crypto hashes TextEncoder UTF-8 bytes, including
  empty text. Both full 64-character digests are shown. Changed bits are
  counted by XOR; the percentage is measured for these two outputs, never
  a promise that exactly half always change. No API call or transaction.
  Identical inputs show 0%; different inputs explain the avalanche effect,
  typically near half the bits, without requiring a 100% difference.
- **Signatures:** the current adapter reuses `generate_wallet`,
  `sign_message`, `verify_signature`: secp256k1, ECDSA with SHA-256, UTF-8
  messages, DER signatures encoded as hex. Empty and whitespace messages
  are preserved. Integrity/signing-key verification is not encryption or
  real-world legal identity.
- **Merkle:** the adapter hashes each example text leaf once with
  `sha256_hex`, then calls the existing `build_merkle_tree`. Parents hash
  the concatenated **hex strings** as UTF-8, not concatenated raw bytes.
  Odd final hashes are duplicated to form pairs. One leaf's root is that
  leaf hash. Zero leaves produce `[[SHA256("")]]`. Actual returned levels
  are displayed, including any duplicated intermediate node the existing
  implementation returns. Changes compare actual hashes at matching
  level/index positions; nodes removed when the shape changes are not
  drawn. Existing proof generation/verification is reused for this same
  tree, solely inside the lab endpoint.

This is an unsalted example-text tree. Real blocks use already-hashed
transaction IDs as leaves; salted claim trees use their separate existing
claim encoding. The lab does not create blocks, claims or production proofs.

## API contracts

All endpoints belong to the existing `api.wallet_api:app`:

| Method/path | Request | Public response |
| --- | --- | --- |
| POST `/api/labs/signatures/keys` | No body | `key_handle`, full `public_key_hex`, `address`, `expires_in_seconds`, `curve` |
| POST `/api/labs/signatures/sign` | `key_handle`, `message` | Public key fields above, exact `message`, `signature_hex` |
| POST `/api/labs/signatures/verify` | `message`, `signature_hex`, `public_key_hex` | `valid` boolean from existing verifier |
| POST `/api/labs/signatures/keys/{handle}/reset` | No body | `cleared` boolean; idempotent |
| POST `/api/labs/merkle` | `leaves`: text list, optional `proof_index`: zero-based integer | `leaf_hashes`, actual `levels`, `root`, optional `proof`: `index`, `siblings` (hash/left-or-right), `valid` |

Messages: at most 10,000 characters. Public key/signature strings: at most
260/1,024 characters. Merkle: at most 16 leaves, 2,000 characters per leaf.
Invalid request shapes/limits or nonexistent proof indices return 422.
Malformed key/signature encodings within limits produce `valid:false`.
Unknown/expired signing handles return 404; key capacity exhaustion returns
429. Responses never include private keys.

## Isolation and cleanup

Keys are disposable objects in a bounded dictionary **inside the existing
adapter**, guarded by a separate lab lock. They never enter `wallet_store`,
the PoS registry, signed credential store, mempool or Network. A later
signing action needs this server-side key, so a stateless design would
require exporting key material; this implementation does not do that.

At most 64 keys exist per process. Handles expire after 15 minutes and are
unusable thereafter; expired entries are lazily removed on key operations.
Lab reset deletes only that lab's current handles. Replacing a key deletes
the old handle. Leaving the page requests cleanup with `sendBeacon`, best
effort; expiry covers interrupted requests/disconnected browsers. Reset
during key generation discards the late result and requests deletion of
its newly returned handle. Process restart discards all lab keys.

The shared journey reset does not clear lab keys. Lab reset never calls
`/api/session/reset`. Deleting a signing key does not invalidate existing
signatures: public verification remains possible.

Each lab has independent state and guards late responses after its reset.
User/backend text is rendered with DOM text properties, not interpreted
as HTML. Lab state is not saved across reloads. This is an educational,
single-server simulation without authentication or independently secured
validators.

## Checks

```text
python -m pytest -q
node --check ui/labs.js
```

Node.js is required for behavioral UI tests. These tests execute handlers
in Node VM, use real Web Crypto vectors, and exercise reset/stale-response
guards. They are separate from browser verification. API tests compare
Merkle outputs/proofs with existing backend fixtures and verify signature
integrity, wrong keys, cleanup/limits and journey isolation.

## Khối & Chuỗi khối — combined workspace

Open `/ui/labs.html#blocks`. Legacy `#block` and `#blockchain` URLs open
this same workspace. There is one navigation entry, one browser-owned chain
snapshot and one reset action. The chain remains while switching lab tabs;
reload/page exit clears it. No additional Network, server-side chain store,
wallet handle or worker is introduced.

Entering initializes the real canonical genesis via the existing chain API.
Cards display Genesis → Block #1 → Block #2 with connecting arrows in a
horizontally scrollable, keyboard-focusable track. Mobile cards remain
readable inside the track. Overall chain validity/reason appear above it.
Each card shows height, data preview, timestamp, nonce/difficulty, recorded
and recomputed block hashes, previous_hash, own integrity, linkage and
prefix validity. Expand for the full backend header, serialized transaction,
full hashes and actual validation checks.

The compact “Thêm khối” form accepts arbitrary UTF-8 text, including empty
text and preserved whitespace (4,000 characters). No student/certificate,
issuance date or issuer choice. Difficulty is 2–5; advanced fields retain
version (1–2^31−1) and timezone-aware ISO-8601 timestamp (blank = creation
time). previous_hash is read-only and automatically comes from the actual
chain tip. Merkle root and nonce are derived. Add computes/signs/mines a
candidate through the existing backend and appends only on completed PoW.
No fabricated progress percentages: waiting status, measured attempts/time,
incomplete work and backend rejection reasons are separate outcomes.

| Method/path | Request | Public response |
| --- | --- | --- |
| POST `/api/labs/blockchain/init` | No body | Canonical genesis and actual validation |
| POST `/api/labs/blockchain/add` | `chain`, `data`, difficulty 2–5, optional version/timestamp | Snapshot; append only after completed PoW; measured mining and candidate |
| POST `/api/labs/blockchain/validate` | `chain` | Core validity/reason and per-block own integrity, link, prefix checks, recomputed transaction hash |
| POST `/api/labs/blockchain/edit` | `chain`, non-genesis `height`, different `data` | Edited copy with retained evidence; before/after and actual validation |
| POST `/api/labs/blockchain/recompute` | `chain`, edited non-genesis `height` | Updated tx_id/Merkle/recorded hash for that block; retained signature/nonce; unchanged descendants |

Existing `/api/labs/block/{build,mine,edit}` endpoints remain available for
compatibility and keep their calculations/contracts. The UI uses the chain
API rather than a second standalone Block state.

Click edit on a non-genesis card to edit directly there. Draft typing does
not replace the input, mutate the chain or claim validation. Explicit edit
immediately checks the changed public copy while retaining tx_id, signature,
stored Merkle root, nonce and recorded hash. It does not re-sign, re-mine
or repair. Header hash can stay unchanged because it hashes the recorded
Merkle root; the recomputed transaction hash and validator detect corruption.

Direct block integrity, previous_hash linkage and prefix validity are
separate. Editing a middle block can invalidate later prefixes while those
blocks' own hashes/proofs and links remain correct. Explicit recompute is
a separate action: it updates that block's tx_id, Merkle and recorded hash,
leaving the old signature/nonce and next block's previous_hash unchanged.
The next link then breaks; recomputation does not restore signatures, PoW
or consensus. A damaged chain cannot be extended; reset starts a fresh genesis.

Backend Blockchain, Block, Transaction, SHA-256, Merkle and mine_block perform
all calculations. The ledger requires an ISSUE container with a unique
credential_id; a disposable wallet signs `{credential_id: UUID, lab_data:
text}`. This is a teaching representation, not guided credential metadata
or evidence of a real certificate. Core transaction/ledger validation is
unchanged. Genesis must match the backend; no arbitrary transaction shapes
or genesis editing. Core is_chain_valid() provides its real first failure;
recorded-hash comparison is an additional lab check because Block computes
its hash from its header rather than maintaining an immutable stored hash.

At most **12 blocks plus genesis**, 4,000 text characters per block. Mining
uses the existing nonce loop with the same **200,000 search hashes or three
seconds** guard on the disposable instance. Incomplete work does not append;
retry starts at nonce zero. Measured search time includes the guard and does
not measure energy. Concurrent mining returns 429, invalid inputs/limits 422,
missing target 404, invalid-chain append or no-op recompute 409.

Reset starts only this lab's genesis; object-identity guards discard late
initialization/mining/edit replies. No private keys survive a request or
appear in responses. Guided wallets/chains/mempools/stakes/reset_count,
Explorer and every other lab remain untouched. No expiry/worker cleanup is
needed for this public snapshot; retained-network labs keep their existing
lifecycle. User/backend data use textContent, including card editors/details.

Tests cover the production models, hashes/signatures/PoW, optional headers,
automatic previous_hash, middle edits, broken links after recompute, bounds,
incomplete work and isolation. Behavioral Node-VM tests cover connected
cards/details, repeated actions, safe rendering, edit-input identity,
combined reset/stale replies and legacy-URL navigation. These are automated
checks, not browser evidence.

## Added lab: PoW–PoS comparison

`POST /api/labs/consensus/run` accepts `mode` (`pow` or `pos`), optional
`holder_name`, `title`, `issue_date`, `node_online` and `include_sample`.
The metadata defaults match the guided sample; text/date validation reuses
the existing credential API rules. Boolean flags are strict, both default
true, and let users explicitly try offline-node/empty-mempool outcomes.
Clients cannot supply difficulty, validator, key, transaction or stake.

Every call creates a **fresh, isolated single-node Network**, using the
existing default registry/seed/stake mode. A disposable issuer wallet signs
a UUID credential's existing ISSUE payload through `Transaction.sign()`;
`Node.submit_transaction()` admits it. The chosen mode calls
`Node.mine_pending()` (default difficulty 3) or `Node.forge_pos_pending()`
with no validator argument. These methods already broadcast; the adapter
does not broadcast again. There are no peers in this comparison exercise.

The public response includes `created`, `stage`, verbatim `reason`,
`submission`, canonical `transaction` and `block`, `transaction_ids`,
issuer identity, actual PoS `signer`, public validators/stake/selection
weights, `stake_mode`, `seed`, pending count, chain validity/reason, elapsed
`seconds` and `elapsed_scope`. Both elapsed values measure the complete
Node call, excluding setup/signing/submission, API response and worker
cleanup. `backend_timing` retains the backend's narrower measurements:
PoW nonce search; PoS forge/sign/rightful-proposer validation. `attempts`
comes directly from PoW's backend result, and is null for PoS. Time is one
local measurement, not energy consumption or a universal benchmark.

PoS signer metadata is matched by the block's validator address while
holding this network's node lock. Issuer and validator keys remain
distinct. No shared-session lock, wallet store, lab key handles or guided
Network are involved. Registry stake/selection/fork rules are unchanged;
`sync_with_blockchain()` is never called. Selection percentages are stake
weights among eligible validators, not guaranteed observed frequencies.

HTTP 200 also represents expected backend rejections (`created=false`),
with the original reason and pending count **before disposal**. Invalid
inputs return 422; unexpected failures return a clear 500. Workers stop in
`finally` after releasing node locks, on both success and failure. No lab
network/keys are stored after a call. Reset clears only local comparison
inputs/results; it does not cancel a running backend operation, whose late
result is ignored and whose worker still cleans up. No reset API is needed.

Run each mode without changing the sample to compare equivalent fields.
Each run generates fresh issuer/validator keys, credential ID, transaction
nonce/timestamp and block timestamp, so tx IDs, signatures, hashes and
selected validator may differ. Editing sample/condition inputs clears
both results to prevent comparing different experiments. Full public
identities/hashes/seed/timing are in expandable technical details.
The network-sync and tamper labs are described below. Block Explorer is now
available at `/ui/explorer.html`: create a guided block, open Explorer and inspect
its transactions. It reads only the shared guided network, never these lab networks.

## Added lab: network synchronization

`/ui/labs.html#network` uses a retained **isolated three-node Network**.
Node-1/2/3 are simulated workers in the same server, communicating through
queues; 5001–5003 are labels, not HTTP servers or separate computers.
Initialize → take Node-3 offline → create the sample PoW block → observe
Node-1/2 ahead and verify the credential on each node → bring Node-3 online.
The user may refresh or manually sync without changing node status.

| Method/path | Request | Response |
| --- | --- | --- |
| POST `/api/labs/network` | No body | 201: opaque `lab_handle` and initial snapshot |
| GET `/api/labs/network/{handle}` | No body | Actual snapshot |
| POST `/api/labs/network/{handle}/nodes/Node-3/status` | Explicit strict `online` boolean | `changed`, `catch_up_requested`, snapshot; repeated requests are no-ops |
| POST `/api/labs/network/{handle}/mine` | No body | `mined`, verbatim backend rejection `reason`, canonical `block` on success, snapshot |
| POST `/api/labs/network/{handle}/sync` | No body | `completed` for **all three**, `reason`, fresh snapshot |
| POST `/api/labs/network/{handle}/reset` | No body | Idempotent `cleared`; stops workers and deletes this handle |

Snapshots include each node's status, height (excluding genesis), block
count (including genesis), full tip hash, pending count, chain validity and
backend validity reason. After sample creation, each node's verification
includes actual status, checks, reason and on-chain metadata. The verifier
and chain validator receive this lab network's `pos_registry` and authorized
issuers. The retained signed transaction is **not** used as proof of issuance.
`VERIFIED` here verifies the on-chain record by ID; no presented document
is compared. `NOT_FOUND` on an offline stale node can mean that its local
chain has not received the credential, not that the credential is invalid.

The snapshot also returns public issuer metadata, canonical signed ISSUE,
credential ID, mining result, expiry, actual backend events and separate
agreement/validity flags. Agreement requires both height and tip hash;
validity is independently checked. `all_nodes_synchronized` additionally
requires all three nodes to be ONLINE. Equal pending counts prove nothing
about chain agreement. Full hashes, signatures and checks are collapsed in
technical details; private keys are never returned.

The disposable issuer signs through the existing `Transaction.sign()`.
Node-1 submits through `submit_transaction()` and mines through
`mine_pending()` with its unchanged default difficulty **3**. Both methods
already broadcast. One sample block is allowed per network; further mining
returns 409 and asks for this lab's reset. Failed backend admission/mining
keeps the same signed transaction for retry and does not delete pending
transactions to hide failure. Unknown/reset/expired handles return 404,
invalid status bodies return 422, capacity exhaustion returns 429, and
unexpected backend failures return a clear 500. Only Node-3 is controlled
by this scenario; unknown/control-unavailable node IDs return 404.

`go_online()` already queues `SYNC_REQUEST`; reconnect adds no redundant
manual sync. Manual sync calls `Network.sync_all_nodes(online_only=True)`,
which selects/copies chains using existing backend logic and returns None.
Its response therefore describes observed snapshots, not an invented
backend success return. Offline nodes retain their local chain. Mining
and catch-up queue propagation are asynchronous. The UI polls real GET
snapshots for at most **5 seconds**, with a 2-second maximum per read;
timeout reports lack of confirmation rather than success. No polling occurs
while adapter/node locks prevent queue workers from advancing.

Lifecycle follows the existing disposable-lab pattern: separate dictionary
in the current adapter, bounded to **8 networks**, opaque per-page handles,
15-minute fixed lifetime, page-exit best-effort cleanup and app-shutdown
cleanup. A daemon expiry timer stops workers even if the client disappears;
operations also enforce expiry. Reset serializes with lab mutation/mining,
stops workers without holding their node locks, and deletes the old handle.
The lab lock coordinates API/reset; node locks separately coordinate worker
activity. Per-node snapshots are consistent but not globally atomic.
Handles require the documented **single-process** app; restart loses them.

Reset, stale-response guards and page-exit cleanup affect only this network
lab. Guided wallets/credentials/network, signature handles, comparison
results, SHA and Merkle state remain independent. Guided reset also leaves
lab networks alone. UI mutations cannot overlap; resetting during snapshot
polling cancels the read and ignores old responses. A late initialization
after page exit disposes its newly returned handle. Interrupted cleanup has
expiry as a fallback. No consensus/stake/key rules or backend modules change.

Regression coverage includes real offline propagation/catch-up, correct
registry forwarding, equal-height divergent tips, invalid chains, rejection
reasons, isolation, reset/mining serialization and worker/timer shutdown.
Node-VM tests exercise controls, bounded polling, timeout, errors, stale
responses and navigation. They remain separate from real browser checks.

## Added lab: local tamper detection and recovery

Open `http://127.0.0.1:8000/ui/labs.html#tamper`. This is a **separate retained
three-node queue-based Network**, not the guided network or network-sync
lab. Create a sample chain → wait for VERIFIED on all three nodes → edit
the title on Node-2 → inspect actual validation failures → explicitly sync
to recover. Only this lab's reset/close deletes its handle and stops workers.

| Method/path | Request | Response |
| --- | --- | --- |
| POST `/api/labs/tamper` | No body | 201: handle, actual preparation/readiness and node snapshots |
| GET `/api/labs/tamper/{lab_id}` | No body | Actual validator/verifier snapshots; no automatic repair |
| POST `/api/labs/tamper/{lab_id}/edit` | Only `{"title":"Changed title"}` | Snapshot after local corruption; title trimmed, required, max 200 characters |
| POST `/api/labs/tamper/{lab_id}/sync` | No body | Snapshot after existing backend synchronization; completion requires validation |
| DELETE `/api/labs/tamper/{lab_id}` | No body | Idempotent `cleared`, worker shutdown and handle deletion |

Responses expose `lab_id` (also `lab_handle` for the shared snapshot format),
credential ID, original/edited titles, public issuer/transaction/block data,
expiry and `prepared`, `ready`, `tampered`, `restored` flags. `prepared` means
Node-1 mined the sample, not that peers have received it. `ready` requires
all three ONLINE with matching height/tip, valid chains, VERIFIED and the
original title. `restored` additionally requires a prior edit. Per-node
snapshots include local title, height excluding genesis, block count,
online status, pending count, header tip hash, validity/reason and actual
credential checks/status/info. Metadata from an INVALID result is untrusted
local content, not an accepted presented document. No private keys are returned.

The existing sample helper generates a disposable issuer, signs ISSUE with
`Transaction.sign()`, submits on Node-1 and calls `mine_pending()` at default
difficulty **3**, using their existing broadcasts. Propagation is asynchronous.
The UI polls GET outside backend locks for at most **5 seconds** (at most
2 seconds per read); timeout never means success. An expected mining rejection
returns the backend reason and keeps pending data until explicit reset or
expiry. Unexpected preparation failure cleans an unreachable network before
returning 500. Failed sync leaves its network available for inspection.

Editing is allowed only after all three have confirmed the original sample,
and targets **Node-2, block #1, that sample's sole ISSUE payload.title**.
No arbitrary paths/nodes/genesis edits are accepted. Blank/unchanged titles
and extra fields return 422; premature/repeated editing before recovery or
sync before any edit returns 409. Missing/reset/expired/wrong-type handles
return 404; capacity returns 429. Network-lab routes also reject tamper
handles, preventing cross-lab mutation through a different endpoint.

The lab lock serializes preparation/edit/sync/reset/expiry. Editing takes
node locks in the backend's sorted node-ID order and deep-copies Node-2's
local Blockchain graph before changing its title, preserving internal aliases
and preventing accidental sharing with peers. It keeps credential ID, tx_id,
signature, stored Merkle root and header fields unchanged. It does not re-sign,
re-hash, mine, broadcast or automatically synchronize corrupted data.

In this backend a Block does not cache a hash field: `tip_hash` and
`stored_tip_hash` report `compute_hash()` of its retained header. Since the
header Merkle root commits to retained tx_ids, that hash stays unchanged after
a payload-only edit. The existing transaction validator independently checks
`tx_id == compute_hash()` over signed transaction data, detects the changed
title and returns its real rejection text. Node-2 therefore has an invalid
chain and INVALID credential, while Node-1/3 remain valid and VERIFIED.
Equal header hashes alone do **not** prove valid contents.

Recovery calls `Network.sync_all_nodes(online_only=True)` with no manually
saved-chain restoration, replacement Network or validation-rule changes.
Existing backend logic validates peers with `pos_registry` and can replace an
invalid local chain from a valid peer even at equal height/header hash/work.
Only observed original titles, valid matching tips and VERIFIED everywhere
produce `restored=true`. A failed/incomplete recovery keeps the failure
visible. Backend reorganization may retain old local data in its internal
side-branch history; recovery here concerns the active chain. Recovery cannot
legitimize the edited title or undo an authorized revocation on a valid chain.

This differs from the guided journey's presented-document comparison:
that flow edits a presented copy while leaving the chain unchanged; this
lab intentionally corrupts one isolated local blockchain copy. Both use
existing backend verification semantics. Three queue workers on one server
are not three independently secured physical machines or production consensus.

Lifecycle reuses the retained-network store and shared **eight-network**
capacity, fixed **15-minute** expiry timers and application-shutdown cleanup.
No duplicate store or adapter is introduced. Reset is idempotent and joins
workers without holding node locks. Page exit performs DELETE best effort;
expiry is the fallback if the request is interrupted. Handles and live state
are lost on server restart; use one server process. UI identity/abort guards
discard stale replies after reset, forbid overlapping mutations and never
automatically sync after editing. User/backend titles are rendered as text.

Tests cover real preparation/corruption/recovery, unchanged peer data and
transaction/header metadata, matching registry forwarding, wrong handle
types, rejected inputs/lifecycle actions, pending failure preservation,
reset/sync serialization, isolation, expiry and worker shutdown. Node-VM
tests cover controls, safe rendering, explicit recovery, polling/timeouts,
errors, navigation and stale replies; these are not browser verification.
