# Chain-Breaker

A working, minimal scripture-preservation ledger.

Chain-Breaker anchors content-addressed document manifests and curator
attestations in a proof-of-work blockchain. It is intentionally **not a
cryptocurrency** in this release; the currency/tokenomics features from earlier
prototypes have been removed because they were not safe.

## What works now

- Deterministic genesis block with hard-coded specification.
- SHA-256 / double-SHA-256 hashing and Merkle trees.
- Ed25519 curator keys and attestation signatures.
- Content-addressed document archive (store by SHA-256 hash).
- Proof-of-work block mining and chain validation.
- Difficulty retargeting that moves in the correct direction.
- Canonical binary serialization with explicit little-endian encoding.
- Defensive bounds checking in all decoders.

## What was removed

- Broken cached-hash mining loop.
- Trusted-stored-hash proof-of-work bypass.
- Non-public-verifying E8 "quantum-resistant" signature claims.
- Authority-name spoofing (now keys are bound to curator IDs).
- Public-key-string authorization.
- Floating-point consensus fields.
- Truncated transaction / Merkle hashes.
- 700 MB of copyrighted bibles from the source tree (replaced with a small
  public-domain sample set and a downloader script for users who supply their
  own legally obtained texts).
- Duplicate `chain-breaker/` and root-level prototype implementations.

## Install

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## Quick start

Print the canonical genesis block:

```bash
chainbreaker genesis
```

Generate a curator key:

```bash
chainbreaker curator generate --out curator.json
```

Add a document to the archive:

```bash
echo "In the beginning was the Word." > john.txt
chainbreaker archive add john.txt --title "John 1:1 sample" --language en
```

Create and attest a scripture transaction:

```bash
cat > tx.json <<'EOF'
{
  "version": 1,
  "type": "scripture",
  "body": {
    "ref": "John 1:1",
    "content_hash": "PUT_HASH_HERE"
  },
  "witnesses": []
}
EOF
chainbreaker curator attest --wallet curator.json --curator-id my-curator \
  --transaction tx.json --out attested-tx.json
```

Mine it into the ledger:

```bash
chainbreaker node mine attested-tx.json
```

Verify the ledger:

```bash
chainbreaker node verify
```

## Development

```bash
pytest -v
ruff check chainbreaker tests
mypy chainbreaker
```

## License

MIT
