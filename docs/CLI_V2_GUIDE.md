# Chainbreaker Protocol v2 CLI Guide

This guide covers the `chainbreaker v2` command suite.

## Archive commands

### `chainbreaker v2 archive add`

Create a canonical `chainbreaker-manifest-v1` manifest for a file.

```bash
chainbreaker v2 archive add   --data-dir ./archive   --file document.txt   --title "My Document"   --media-type text/plain   --language en   --source "uploaded by author"   --source-identifier "urn:example:1"   --acquisition-date 1754400000   --license "CC0"   --output-manifest manifest.json
```

Output includes `manifest_hash`, `content_hash`, `byte_length`, `network_id`,
and `schema_version`. Files are written atomically; use `--force` to overwrite.

### `chainbreaker v2 archive verify`

Recompute the content hash and manifest hash from stored bytes and verify the
network ID and schema version.

```bash
chainbreaker v2 archive verify --data-dir ./archive --manifest-hash <hash>
```

## Attestation commands

### `chainbreaker v2 attest create`

Sign a manifest at a historical block height. The curator key must be active
at that height. Private keys are read from files only.

```bash
chainbreaker v2 attest create   --ledger ledger.json   --manifest manifest.json   --curator-id alice   --block-height 2   --private-key alice.sk.hex   --output att.json
```

### `chainbreaker v2 attest verify`

Verify a historical attestation against registry state at the attestation
height.

```bash
chainbreaker v2 attest verify   --ledger ledger.json   --attestation att.json   --manifest manifest.json   --block-height 2
```

## Security notes

- Never pass private-key bytes on the command line.
- The CLI only prints curator IDs and public keys; private-key material is
  never emitted in output, errors, or logs.
- Atomic writes ensure a failed operation does not leave a half-written file.

## Alpha storage limitations

- Streaming SHA-256 hashing supports files up to a soft 1 GB ceiling.
- Large files should be archived in chunks once chunking is implemented.
