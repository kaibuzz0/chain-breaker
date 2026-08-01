# Header v2 Implementation Checklist

This checklist tracks Milestone 4A: header v2 data structures and
serialization.  It must be completed before moving to Milestone 4B.

## Scope restriction

Only the following may change in this milestone:

- `chainbreaker/block.py` — add `registry_root` to header dataclass
- `chainbreaker/codec.py` — add v2 header encode/decode
- `tests/` — add v2 header tests

The following must NOT change:

- genesis constants
- mining
- proof-of-work
- chain validation
- CLI
- witness validation
- `governance.py`
- `registry_state.py`

---

## Serialization checklist

- [ ] `BinaryCodec.encode_header_v2` returns exactly 149 bytes.
- [ ] Field offsets match the table in `docs/HEADER_V2_MIGRATION_PLAN.md`:
  - type marker at offset 0, size 1
  - version at offset 1, size 4
  - prev_hash at offset 5, size 32
  - merkle_root at offset 37, size 32
  - registry_root at offset 69, size 32
  - timestamp at offset 101, size 8
  - target at offset 109, size 32
  - nonce at offset 141, size 8
- [ ] Multi-byte integers are little-endian.
- [ ] Hash fields are 32 raw bytes, not hex strings.
- [ ] Type marker is `0x02`.
- [ ] Version `2` is encoded.
- [ ] Canonical round-trip holds:
  ```text
  decode(encode(header)) == header
  encode(decode(bytes)) == bytes
  ```

## Deserialization checklist

- [ ] `BinaryCodec.decode_header_v2` parses 149-byte input correctly.
- [ ] Missing bytes raise `CodecError`.
- [ ] Wrong type marker raises `CodecError`.
- [ ] Version mismatch raises `CodecError`.
- [ ] Hash fields are validated to be exactly 32 bytes.
- [ ] Returned dict has keys:
  `version`, `prev_hash`, `merkle_root`, `registry_root`, `timestamp`, `target`, `nonce`.

## Compatibility checklist

- [ ] v1 header decode still works through a dedicated v1 path or legacy test helper.
- [ ] v2 header bytes cannot be parsed as v1.
- [ ] v1 header bytes cannot be parsed as v2.
- [ ] Malformed headers (wrong length, wrong marker, truncated fields) are rejected.

## Security checklist

- [ ] No implicit default for `registry_root`.
- [ ] No `time.time()` or wall-clock in canonical encoding.
- [ ] No mutable global state in codec functions.
- [ ] Header validation rejects non-canonical integer widths or hash lengths.

## Test checklist

- [ ] Exact 149-byte serialization test.
- [ ] Fixed field offset test (read individual bytes at known offsets).
- [ ] Round-trip identity test.
- [ ] v1-vs-v2 rejection test.
- [ ] Malformed header tests:
  - wrong type marker
  - truncated header
  - extra bytes
  - wrong version
- [ ] Existing v1 tests still pass.

## Verification gates

Run before claiming 4A complete:

```text
python -m pytest -v
python -m pytest --cov=chainbreaker --cov-report=term-missing
python -m ruff check chainbreaker tests
python -m mypy chainbreaker
python -m build
python -m pip_audit -r requirements.txt
python -m bandit -r chainbreaker
```

---

## Definition of done

- [ ] This checklist is fully checked.
- [ ] The commit `implement header v2 data structures` is pushed.
- [ ] No other consensus code was modified.
- [ ] Branch is ready for Milestone 4B review.
