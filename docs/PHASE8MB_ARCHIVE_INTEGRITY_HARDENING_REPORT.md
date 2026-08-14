# Phase 8M-B Archive Integrity Hardening Report

**Branch:** `phase8mb-archive-integrity-hardening`  
**Base:** `main` @ `9dabc840b903ae4c350290dfb31ba88353e21b12`  
**Date:** 2026-08-14  
**Scope:** Archive library integrity only. 8M-C/D/E not started.

## 1. Executive Summary

Phase 8M-B makes the Python `Archive` API authoritative for archive integrity.
Before this phase, the CLI `v2 archive verify` command contained stronger
verification logic than the library: the library's `verify_manifest()` only
checked the manifest hash, `get_document()` returned raw bytes without hash
recheck, and `add_document()` wrote object and manifest files non-atomically.

This phase:

1. Makes `Archive.add_document()` atomic using the existing
   `chainbreaker.storage.filesystem.atomic_write()` + `fsync_dir()` helpers.
2. Makes `Archive.get_document()` verify the content hash **by default**;
   adds an explicitly-named `get_document_unverified()` for callers that
   already hold an independent integrity guarantee.
3. Adds `Archive.verify_document(manifest_hash)` for full manifest+content
   binding verification (manifest bytes hash, schema, content hash, byte length).
4. Adds `Archive.get_verified_document(manifest_hash)` returning the validated
   manifest and content together.
5. Converts CLI `v2 archive verify` into a thin caller of
   `Archive.verify_document()` instead of duplicating logic.
6. Adds 15 regression tests proving atomicity, corruption detection, and
   backward compatibility.

## 2. Read-Only Path Map

Created as:
`docs/PHASE8MB_ARCHIVE_INTEGRITY_ACCEPTANCE_PATH_MAP.md`

Confirmed outside-review claims:

| Claim | Status |
|---|---|
| Non-atomic archive writes | **CONFIRMED** |
| `get_document()` returns content without hash recheck | **CONFIRMED** |
| `verify_manifest()` validates only manifest, not content binding | **CONFIRMED** |
| CLI stronger than library | **CONFIRMED** |

## 3. Files Changed

Core:
- `chainbreaker/archive.py`
  - `add_document()` now uses `atomic_write()` and `fsync_dir()`.
  - `get_document(content_hash, *, verify=True)` now recompute-hashes by default.
  - New `get_document_unverified()` for explicit unsafe reads.
  - `verify_manifest()` kept as the fast manifest-only check.
  - New `verify_document()` for full binding verification.
  - New `get_verified_document()` returning manifest + content.
- `chainbreaker/cli_v2.py`
  - `v2 archive verify` now delegates to `Archive.verify_document()`.

Tests:
- `tests/test_phase8mb_archive_integrity_hardening.py` — 15 new regression tests.
- `tests/test_cli_v2.py` — updated expectation: mutating manifest bytes now
  fails with "manifest hash mismatch" before the network-id check, which is
  the correct stronger behavior.

Docs:
- `docs/PHASE8MB_ARCHIVE_INTEGRITY_ACCEPTANCE_PATH_MAP.md`
- This report.

## 4. Invariants Proven by Tests

1. `Archive.add_document()` never leaves partial/temp files behind.
2. `Archive.get_document()` verifies the content hash by default and rejects
   corrupt or replaced objects.
3. `Archive.get_document_unverified()` provides an explicit opt-out path.
4. `Archive.verify_document()` rejects:
   - corrupt manifest bytes,
   - missing referenced objects,
   - content hash mismatch,
   - content length mismatch,
   - truncated compressed objects.
5. `Archive.get_verified_document()` returns a validated (manifest, content)
   tuple.
6. Existing valid archives remain readable.
7. Re-adding identical data yields identical manifest/content hashes.
8. CLI `v2 archive verify` succeeds for valid archives and fails safely on
   corruption.

## 5. Frozen-Vector / Compatibility Impact

- No Protocol V2 constants, genesis artifacts, or frozen vectors were changed.
- The canonical hashing and compression paths are unchanged, so all previously
  valid archives remain valid.
- `verify_manifest()` semantics are preserved as the fast manifest-only check.

## 6. Verification Gates (Local)

| Gate | Status |
|---|---|
| Archive tests old + new | **PASS** (16 tests) |
| CLI archive tests | **PASS** (80 CLI tests incl. archive subset) |
| Core consensus tests | **PASS** (117 tests incl. block/chain/codec/genesis) |
| Storage/network subset | **PASS** (313 tests) |
| Ruff | **PASS** |
| mypy | **PASS** |
| Build | **PASS** |
| Bandit | **PASS** |
| pip-audit | **PASS** |
| Rust verifier | **N/A locally** — CI will run it. |

## 7. Known Limitations / Next Phases

- Archive recovery tooling (e.g. `repair` or garbage collection of orphaned
  objects) is intentionally out of scope for 8M-B; it is a candidate for 8M-E.
- Large-file streaming inside `add_document()` still reads the whole source
  into memory once because `Archive.add_document()` takes `data: bytes`. The
  CLI continues to use `_stream_hash()` for the initial hash and `_safe_read()`
  for the actual storage, matching previous behavior.

## 8. Next Step

Push the branch and open PR. CI must be fully green before 8M-C is authorized.
