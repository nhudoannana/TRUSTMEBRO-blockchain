# TRUSTMEBRO Labs — phase 1

Run the existing single-process app:

```text
python -m uvicorn api.wallet_api:app --host 127.0.0.1 --port 8000
```

Home: http://127.0.0.1:8000/ui/modes.html#labs

Exercises: `/ui/labs.html#sha`, `#signatures`, `#merkle`, `#consensus`, `#network`.
The guided PoW/PoS journey remains `/ui/trustmebro.html`. All pages use
the saved `trustmebro-theme` preference. Other labs remain unavailable.

## Where calculations run

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
The network-sync lab is described below. Tamper and block-explorer labs
remain unavailable.

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
