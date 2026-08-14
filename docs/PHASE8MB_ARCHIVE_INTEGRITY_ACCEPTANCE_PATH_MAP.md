# Phase 8M-B Archive Integrity Acceptance/Verification Path Map

**Status:** read-only, created before any 8M-B code changes.  
**Branch base:** `main` @ `9dabc840b903ae4c350290dfb31ba88353e21b12`.  
**Date:** 2026-08-14.

## 1. Scope

This map documents every archive read/write/verify path in the Python `Archive`
class, the CLI `v2 archive` commands, and any storage path that reaches archive
objects or manifests.  It is a precondition for 8M-B implementation; no code
changes were made while producing it.

## 2. Python Archive API paths

### 2.1 `Archive.add_document()`
**File:** `chainbreaker/archive.py:61`

| Step | Behavior | Integrity property | Risk |
|---|---|---|---|
| Hash input | `HashEngine.hash_single_hex(data)` | Deterministic content hash | None |
| Object path | `objects_dir / hh[0:2] / hh[2:4] / hh` | Content-addressed prefix tree | None |
| Write object | `open(obj_path, "wb"); f.write(zlib.compress(data))` | **Non-atomic**: writes directly to final path | Crash between open and close leaves corrupt/truncated object; no fsync; symlink race possible because file opened by final path |
| Metadata hash | `HashEngine.canonical_json(metadata)` then hash | Captures metadata in manifest | None |
| Build manifest | Includes `content_hash`, `byte_length`, `metadata_hash`, `notes_hash`, network ID, schema version | Self-describing envelope | None |
| Validate manifest | `validate_scripture_body(manifest)` | Schema/field check | None |
| Hash manifest | `HashEngine.hash_single_hex(manifest_bytes)` | Manifest content-address | None |
| Write manifest | `open(mpath, "wb"); f.write(manifest_bytes)` | **Non-atomic**: same risk as object write | Crash between open and close can corrupt manifest; object may exist without manifest or vice versa |
| Return | `manifest_hash` | Caller receives content address | None |

**Finding:** `add_document()` is **not atomic** and has **no fsync**. A crash
after writing the object but before writing the manifest leaves an unreferenced
object. A crash while writing either file can leave a corrupt, content-mismatched
file at the content-address path. Because the file is opened by its final name,
a concurrent symlink attack could redirect the write (Windows/POSIX symlink
races differ, but the code does not protect against either).

### 2.2 `Archive.get_manifest()`
**File:** `chainbreaker/archive.py:155`

| Step | Behavior | Integrity property | Risk |
|---|---|---|---|
| Read file | `open(mpath, "rb"); f.read()` | Reads stored bytes | None |
| Parse JSON | `json.loads(...)` | Deserialization | None |
| Validate | `validate_scripture_body(manifest)` | Schema check | None |
| Return | manifest dict | **Does not recompute hash** | A renamed or corrupted manifest file will be returned as long as it parses and satisfies the schema. The caller is responsible for hash verification. |

**Finding:** `get_manifest()` does **not** verify that the bytes at `mpath`
hash to the requested `manifest_hash`. It trusts the filename.

### 2.3 `Archive.get_document()`
**File:** `chainbreaker/archive.py:171`

| Step | Behavior | Integrity property | Risk |
|---|---|---|---|
| Read file | `open(obj_path, "rb"); f.read()` | Reads stored bytes | None |
| Decompress | `zlib.decompress(compressed)` | Returns original bytes | None |
| Return | bytes | **Does not recompute or check content_hash** | A corrupted, replaced, or truncated object is returned silently. The caller must verify the hash itself. |

**Finding:** `get_document()` is a **pure content fetcher** with no integrity
check. This matches the outside-review claim that the library returns content
without rechecking its hash.

### 2.4 `Archive.verify_manifest()`
**File:** `chainbreaker/archive.py:183`

| Step | Behavior | Integrity property | Risk |
|---|---|---|---|
| Read stored bytes | `mpath.read_bytes()` | Raw read | None |
| Parse JSON | `json.loads(...)` | Deserialization | None |
| Validate schema | `validate_scripture_body(manifest)` | Schema check | None |
| Recompute hash | `HashEngine.hash_single_hex(stored_bytes)` | Byte-level manifest integrity | None |
| Return | `recomputed == manifest_hash` | **Manifest-only verification** | Does not fetch the object or verify `content_hash` binding. A manifest may be valid while its referenced object is missing, corrupt, or replaced. |

**Finding:** `verify_manifest()` verifies the **manifest bytes** but not the
**manifest-content relationship**. This confirms the outside-review claim.

### 2.5 `store_manifest()` / `load_manifest()` / top-level `verify_manifest()`
**Files:** `chainbreaker/archive.py:257-295`

These are thin convenience wrappers around `Archive.add_document()`,
`get_manifest()`, and `verify_manifest()`. They inherit all risks of the
underlying methods.

## 3. CLI `v2 archive` paths

### 3.1 `v2 archive add`
**File:** `chainbreaker/cli_v2.py:994-1103`

| Step | Behavior | Integrity property | Risk |
|---|---|---|---|
| Stream-hash input | `_stream_hash(in_path)` | Streaming SHA-256; 1 GB alpha cap | None |
| Read metadata/notes | `_safe_read()` + hash | Hash only recorded | None |
| Read source bytes | `_safe_read(in_path, max_bytes=ALPHA_MAX_FILE_SIZE)` | Loads whole file once | None |
| Call Archive | `archive.add_document(...)` | See §2.1 | Inherits non-atomic write risk |
| Output manifest file | `_atomic_write(out_path, json.dumps(manifest, ...))` | Atomic via temp+rename | Good |
| Echo summary | JSON with hashes | Informational | None |

**Finding:** The CLI protects its own output file with `_atomic_write()`, but
the **archive library itself does not use atomic writes** for object or
manifest storage. The CLI's stronger local guarantee does not extend into the
archive directory.

### 3.2 `v2 archive verify`
**File:** `chainbreaker/cli_v2.py:1106-1153`

| Step | Behavior | Integrity property | Risk |
|---|---|---|---|
| Load manifest | `archive.get_manifest(manifest_hash)` | See §2.2 | Does not verify filename matches hash here |
| Check network/schema | Compares `network_id` and `schema_version` | Prevents cross-chain/version confusion | Good |
| Recompute manifest hash | Reads `mpath` bytes, hashes, compares | Detects manifest tampering | Good |
| Fetch document | `archive.get_document(content_hash)` | See §2.3 | No integrity check on fetch |
| Recompute content hash | `HashEngine.hash_single_hex(content)` | Detects object tampering | Good |
| Check length | `len(content) == byte_length` | Detects truncation/padding | Good |

**Finding:** The CLI performs the **complete manifest+content verification**
that the library's `verify_manifest()` does not. This is exactly the gap the
outside review identified: the CLI has stronger integrity logic than the Python
`Archive` API.

## 4. Storage subsystem interaction

The storage subsystem (`chainbreaker/storage/`) deals with blocks, headers,
journals, and chain state, not archive objects/manifests. There is no direct
coupling between `Archive` and the storage backend.  Recovery behavior for
archive corruption is therefore limited to whatever the `Archive` class itself
provides: none at present.  A future storage path that embeds manifest hashes
in blocks would depend on `verify_manifest()` for re-validation, so hardening
the library is a prerequisite for any storage-level archive guarantees.

## 5. Claim verification

| Outside-review claim | Status | Evidence |
|---|---|---|
| Non-atomic archive writes | **CONFIRMED** | `Archive.add_document()` writes object and manifest directly to final paths with no temp file or `os.replace`. |
| `get_document()` returns content without rechecking its hash | **CONFIRMED** | `Archive.get_document()` only decompresses; it never hashes the result. |
| `verify_manifest()` validates only the manifest, not the manifest-content binding | **CONFIRMED** | `Archive.verify_manifest()` returns after comparing `hash(stored_bytes) == manifest_hash`; it never touches the object. |
| CLI has stronger verification than the library | **CONFIRMED** | `v2 archive verify` recomputes both manifest hash and content hash; the library method does only the former. |

## 6. Required invariants for 8M-B

1. **Atomicity:** `add_document()` must write each archive file (object and
   manifest) via temp-file + atomic rename, and should fsync before rename where
   practical.
2. **Manifest-content binding:** the library must expose a method that, given
   a manifest hash, verifies both the manifest bytes and the referenced object
   bytes, returning the manifest and content only on success.
3. **No weaker library path:** `verify_manifest()` must be upgraded to the
   full verification, or a new `verify_document(manifest_hash)` method must
   become the canonical API; CLI must call the library rather than reimplement
   the logic.
4. **Defensive reads:** `get_document()` should accept an optional expected
   content hash and raise if the bytes do not match, or a new
   `get_verified_document(content_hash)` should be preferred.
5. **Recovery/diagnostics:** corrupted/missing objects must surface a clear
   error, not return silently wrong bytes.
6. **Frozen-vector safety:** any change must not alter the canonical hash of
   valid existing archive objects or manifests.

## 7. Open questions before implementation

- Should `verify_manifest()` be extended in place (API break for callers that
  expect a cheap manifest-only check) or should a new method be added and the
  old one kept as a fast manifest-hash check?
- Should `get_document()` gain an optional `expected_hash` parameter, or should
  verification be forced through a new method?
- Should `add_document()` return both `manifest_hash` and `content_hash` for
  callers that want immediate verification?
- Is there a Windows-specific atomic-write helper already in the repo
  (`_atomic_write()` in `cli_v2.py`) that should be moved to a shared utility?
