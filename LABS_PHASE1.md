# TRUSTMEBRO Labs — phase 1

Run the existing single-process app:

```text
python -m uvicorn api.wallet_api:app --host 127.0.0.1 --port 8000
```

Home: http://127.0.0.1:8000/ui/modes.html#labs

Exercises: `/ui/labs.html#sha`, `#signatures`, `#merkle`.
The guided PoW/PoS journey remains `/ui/trustmebro.html`. All pages use
the saved `trustmebro-theme` preference. Other labs remain unavailable.

## Where calculations run

- **SHA-256:** browser Web Crypto hashes TextEncoder UTF-8 bytes, including
  empty text. Both full 64-character digests are shown. Changed bits are
  counted by XOR; the percentage is measured for these two outputs, never
  a promise that exactly half always change. No API call or transaction.
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
