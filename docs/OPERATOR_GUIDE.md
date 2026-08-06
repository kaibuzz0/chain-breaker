# Chain-Breaker Operator Guide

This guide covers running Chain-Breaker v2.0.0-alpha as a local operator.

## Installation

```bash
pip install dist/chainbreaker-0.2.0-py3-none-any.whl
hon --help
```

If installing from source:

```bash
python -m build
pip install dist/chainbreaker-0.2.0-py3-none-any.whl
```

## Quick start

### 1. Generate a curator key pair

```bash
hon curator generate --name alpha-curator --output-dir ./keys
```

This writes `alpha-curator_sk.hex` and `alpha-curator_pk.hex`.

### 2. Build a genesis chain

```bash
hon chain init   --name alpha-chain   --curator-pubkey ./keys/alpha-curator_pk.hex   --output ./chain
```

### 3. Mine and add a block

```bash
hon block mine --chain ./chain --difficulty-bits 20 --output ./mined_block.bin
hon block add --chain ./chain --block ./mined_block.bin
```

### 4. Verify the chain

```bash
hon chain verify --chain ./chain
```

## Curator actions

### Register a new curator

```bash
hon curator register   --chain ./chain   --name beta-curator   --pubkey ./keys/beta-curator_pk.hex   --curator-private-key ./keys/alpha-curator_sk.hex   --output ./register_action.bin
```

Then mine and add a block containing the action:

```bash
hon block mine --chain ./chain --actions ./register_action.bin --difficulty-bits 20 --output ./mined_block.bin
hon block add --chain ./chain --block ./mined_block.bin
```

### Rotate a curator key

```bash
hon curator rotate   --chain ./chain   --name alpha-curator   --new-pubkey ./keys/alpha-curator-v2_pk.hex   --curator-private-key ./keys/alpha-curator_sk.hex   --output ./rotate_action.bin
```

### Revoke a curator

```bash
hon curator revoke   --chain ./chain   --name beta-curator   --curator-private-key ./keys/alpha-curator_sk.hex   --output ./revoke_action.bin
```

## Archive and attestation workflows

### Add an external archive

```bash
hon archive add   --chain ./chain   --file ./evidence.pdf   --output ./archive_record.bin
```

### Verify an archive record

```bash
hon archive verify --chain ./chain --record ./archive_record.bin
```

### Create an attestation

```bash
hon attest create   --chain ./chain   --block-height 3   --curator-private-key ./keys/alpha-curator_sk.hex   --output ./attestation.bin
```

### Verify an attestation

```bash
hon attest verify --chain ./chain --attestation ./attestation.bin
```

## Security practices

1. **Never commit private keys.** Files ending in `_sk.hex` must remain secret.
2. **Use absolute paths or verify relative paths.** The CLI rejects path traversal, but double-check your inputs.
3. **Back up the chain directory.** It contains the ledger and witness records.
4. **Run `hon chain verify` before important operations.** It replays the chain from genesis and catches corruption.
5. **Do not share curator keys across chains.** Each chain should have its own key set.

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | User error (bad arguments, missing files) |
| 2 | System error (I/O, build failure) |
| 3 | Validation or security failure |

## Troubleshooting

### `SecurityFailure: symlink detected`

A path you provided is a symbolic link. Use the real file path or copy the file into the working directory.

### `SecurityFailure: path traversal detected`

A path contains `..` or resolves outside the working directory. Use relative paths within the working directory.

### `ValidationFailure: invalid attestation`

The attestation was signed by a curator who was not active at the claimed block height, or the block height is out of range.
