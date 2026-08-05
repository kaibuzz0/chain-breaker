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


## Security hardening

### Private-key safety

`curator generate` writes the private key with mode `0o600` on POSIX and checks
that group/other bits are zero. It refuses to overwrite symlinks unless
`--force` is given. The public key hex and curator ID are echoed; the private
key bytes never appear in stdout, stderr, transaction JSON, or logs.

### Atomic writes

All file-producing commands use a same-directory temporary file and
`os.replace`. If the write fails, the previous file remains intact. This applies
to ledgers, blocks, governance transactions, attestations, manifests, and
private keys.

### Path traversal and symlinks

Relative paths containing `..` are rejected. Security-sensitive outputs refuse
to write through symlinks without `--force`. Archive inputs also refuse
symlinks.

### Archive size policy

`v2 archive add` streams SHA-256 in 1 MB chunks. The alpha release hard-rejects
files larger than 1 GB with a clear error. There is no override flag.

### Historical attestation

Attestations are bound to a ledger height, manifest hash, curator ID, and
network ID. Verification resolves the curator registry at the attested
height, so validity depends only on on-chain state, not wall-clock time.

### No networking / no shell

Every v2 command is self-contained. None spawn subprocesses, read environment
variables for behavior, or make network requests.
