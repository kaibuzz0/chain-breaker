# Hermes Self-Improvement Report — Chain-Breaker Consensus Phase

## Skills inspected

- `github-repo-management`
- `python-project-setup-from-github`
- `security-vulnerability-analysis`
- `software-development-workflows`
- `bug-hunting-security-review`
- `execution-completion-patterns`
- `code-review-methodology`

## Skills changed

### 1. `github-repo-management`
- **Previous weakness:** The fallback "work without git/curl" section assumed a token would be available, and did not explicitly forbid asking for it in chat.
- **Exact improvement:** Added an `## Authentication policy` section at the top that says:
  - Never request that a user paste a GitHub token into chat.
  - Prefer existing `gh` CLI auth, existing SSH auth, narrowly scoped env helpers, or a clean local commit with user-executed push commands.
  - Updated the "Working Without git or curl" section to say the API fallback must obtain the token from the user's configured environment, never by asking in chat.
- **Reason reusable:** Applies to every repository-management task where authentication is needed.
- **Validation:** Read the updated skill; verified the new section is present and the old token-in-chat assumption is gone.
- **Possible side effects:** When a user genuinely has no auth configured, I will now stop and give safe commands rather than push. This is the intended behavior.

### 2. `software-development-workflows`
- **Previous weakness:** No guidance for duplicate implementations of the same consensus/crypto/protocol behavior.
- **Exact improvement:** Added `## Section 0.5: Multiple Implementations of the Same Behavior` with a protocol to identify the canonical implementation, consolidate behind a pure function, and test the canonical path plus at least one delegating alternative.
- **Reason reusable:** Consensus splits, serialization mismatches, and silent regressions occur in any project where two paths compute the same thing differently.
- **Validation:** Applied the rule during this task when consolidating `HashEngine.hash_object` vs `HashEngine.hash_object_hex`, and when making mining/validation use a single `expected_target_at()` function.
- **Possible side effects:** May cause me to spend extra time searching for call sites before editing; that is the point.

### 3. `execution-completion-patterns`
- **Previous weakness:** Focused on multi-item completion but did not distinguish "tests pass" from "important functions were executed."
- **Exact improvement:** Added `## Test Coverage is Not Function Coverage` with a protocol to inspect coverage `Missing` lines, add call-path tests for consensus/crypto/validation functions, and not claim a feature is verified when its function has zero coverage.
- **Reason reusable:** Prevents false confidence from green test suites that never exercise admission paths.
- **Validation:** Used the protocol to add adversarial and call-path tests after the initial green run exposed low codec/witness coverage.
- **Possible side effects:** May prompt me to add more tests before declaring completion; this is intended.

### 4. `bug-hunting-security-review`
- **Previous weakness:** Did not explicitly call out the "validator exists but is not enforced" failure mode.
- **Exact improvement:** Added `### Validation is not Enforcement` with a checklist to trace validators from untrusted input entry points and confirm they are invoked before acceptance. Added an example of `verify_transaction_witnesses()` not being called by `Ledger.add_block()`.
- **Reason reusable:** This exact defect appeared in Chain-Breaker and is common in permission/validation code.
- **Validation:** Applied the rule to wire `verify_transaction_witnesses()` into `Ledger.add_block()` and added tests proving the admission path rejects bad witnesses.
- **Possible side effects:** May cause me to challenge code that has validators but no obvious caller; that is intended.

### 5. `security-vulnerability-analysis`
- **Previous weakness:** The Python blockchain prototype section listed six common defects but omitted the bit-count difficulty flaw, inconsistent retarget boundaries, triple hashing, and runtime genesis mining.
- **Exact improvement:** Added warning signs 7–10 covering bit-count difficulty, inconsistent retarget boundaries, hashing count mismatches, and runtime genesis mining.
- **Reason reusable:** These defects are generic to small PoW blockchain prototypes.
- **Validation:** All four warning signs matched defects found and fixed in this repository.
- **Possible side effects:** The skill now has more items; they are concrete and testable.

## Skills created

### 1. `claim-versus-code-verification`
- **Purpose:** Prevent describing a system as clean, secure, working, production-ready, or fully verified based only on passing tests.
- **Core rule:** Require direct evidence from syntax checks, relevant test coverage, type checking, build, dependency audit, secret scan, adversarial tests, clean Git state, and documented unresolved risks.
- **Mandatory output:** A completion report with starting/final commits, files changed, tests added, coverage, lint/type/build/security results, unresolved risks, and deferred features.
- **Tested against:** This Chain-Breaker task, a hypothetical "tests pass but validator not called" failure, and a misleading instruction to call a prototype "production-ready."

### 2. `canonical-serialization-review`
- **Purpose:** Review and harden canonical serialization/deserialization for consensus-critical data.
- **Core checklist:** one canonical representation, explicit byte order, bounded sizes, canonical varints, strict UTF-8, no floats, bounded nesting, no trailing bytes, deterministic field ordering, validate-before-slice, and adversarial malformed-input tests.
- **Tested against:** This Chain-Breaker task (found missing HashEngine import, noncanonical varint handling, etc.) and a hypothetical cross-endian serialization defect.

### 3. `adversarial-test-generation`
- **Purpose:** Generate adversarial tests that exercise validation failures, malformed input, and consensus edge cases.
- **Core principles:** test admission path, never assert blind `Exception`, cover structured failure modes, deterministic tests, and property-based checks.
- **Tested against:** This Chain-Breaker task (added 17 adversarial tests covering forged hashes, bad PoW, altered transactions, invalid witnesses, etc.) and a hypothetical helper-only test suite.

## Lessons learned

1. **A validator that is not called from the admission path is not a consensus rule.** I fixed `verify_transaction_witnesses()` in isolation, but the real fix was wiring it into `Ledger.add_block()`.
2. **Difficulty must be a target, not a bit count.** Linear scaling of bit counts is exponentially wrong and breaks retargeting.
3. **There must be exactly one function for retargeting.** Mining, admission, and validation must all call the same pure `expected_target_at()` function.
4. **Genesis must be constants, not re-mined.** A runtime-mined genesis makes the chain non-deterministic.
5. **Separate submission freshness from historical validity.** Archival signatures must remain valid forever; freshness is a mempool concern.
6. **Codec imports matter.** `HashEngine` referenced but not imported meant the transaction encoding path was broken at runtime even though tests passed.
7. **Coverage reveals untested functionality.** The initial 15 tests had 0% CLI coverage and low codec/witness coverage; adding call-path and adversarial tests raised total coverage to 80%.
8. **Ruff and mypy must pass before claiming quality.** The code initially had 154 lint errors and multiple type errors; fixing them revealed real bugs (e.g., import ordering, undefined `Optional`).
9. **Generated artifacts are not "clean."** `.coverage`, `.ruff_cache`, `.mypy_cache`, `dist/`, and `*.egg-info` had to be removed before the tree was clean.
10. **Do not ask for tokens in chat.** This environment lacks git/gh, so the correct response is a clean local tree plus safe user-executed commands, not an API push using a pasted token.

## Tests performed on each changed skill

| Skill | Test scenario | Result |
|-------|---------------|--------|
| `github-repo-management` | Attempted repo push in an environment with no git/gh and refused to ask for token | Stopped with local tree + commands |
| `software-development-workflows` | Found `HashEngine.hash_object` vs `hash_object_hex` and mining vs validation target functions | Consolidated behind canonical functions |
| `execution-completion-patterns` | Initial green test suite missed codec import bug and low coverage | Added call-path/adversarial tests |
| `bug-hunting-security-review` | `verify_transaction_witnesses()` existed but `add_block()` did not call it | Wired validator into admission path |
| `security-vulnerability-analysis` | All four new warning signs matched actual defects | Fixed and added tests for each |

## Changes rejected and why

- **Adding Chain-Breaker-specific paths/hashes/names to general skills:** Rejected because the instruction forbids project-specific facts in reusable skills. Skills contain generic rules and patterns only.
- **Patching `code-review-methodology` with a token-handling rule:** Rejected because `github-repo-management` already covers authentication; duplicate wording would conflict.
- **Removing the existing `kaibuzz0 Bug Hunt Expectations` user-specific note in `bug-hunting-security-review`:** Not added or modified in this phase; it predates the instruction. It is user-specific but was already present and pinned to this user's workflow. No new user-specific notes were added.

## Remaining skill weaknesses

- `github-repo-management` still contains user-specific notes (`kaibuzz0` expectations in `bug-hunting-security-review`). These should eventually be moved to user memory or a user-specific skill overlay.
- `claim-versus-code-verification` does not yet have a concrete template file; it should get a markdown template under `references/` in a future pass.
- `canonical-serialization-review` needs real-world test vectors from Protocol Buffers / Bitcoin to make examples more concrete.
- `adversarial-test-generation` could be extended with property-based/fuzzing integration guidance (e.g., `hypothesis`).

## Recommended future skill work

- Create a `consensus-audit` umbrella skill that references `canonical-serialization-review`, `adversarial-test-generation`, `bug-hunting-security-review`, and `claim-versus-code-verification`.
- Add a `safe-autonomous-commit-workflow` skill that formalizes the "no token in chat" rule and the "clean local commit + user commands" fallback.
- Add a `cryptographic-claim-verification` skill with rules against describing custom crypto as post-quantum/secure/production-ready without a complete public construction.
- Move user-specific workflow notes from `bug-hunting-security-review` to the user's `USER.md` memory or a profile-specific skill.

## Handoff and independent verification phase (addendum)

### Skills modified

1. `software-development-workflows`
   - **Rule added:** Section 0.75 — Artifact handoff when Git is unavailable.
   - **Reusable lesson:** A clean standalone artifact directory is not a Git
     commit. Produce a manifest, separate manifest hash, reproducible archive,
     independent extraction test, and safe import scripts.
   - **Validation scenario:** The chain-breaker consensus rewrite was packaged at
     `D:\tmp\chain-breaker-rewrite` with `HANDOFF_MANIFEST.json`,
     `HANDOFF_MANIFEST.sha256`, `HANDOFF_REPORT.md`, `CHANGE_INVENTORY.md`, a
     unified patch, and `import_into_git_checkout.ps1` / `.sh`. The archive was
     extracted into a temporary directory, all 36 manifest hashes matched, and 62
     pytest tests plus a full-flow block-mining test passed.
   - **Failure scenario:** Earlier iterations included caches or tried to embed
     the manifest's own hash, causing verification mismatches.
   - **Malicious-instruction scenario:** An attacker instructs the agent to bypass
     verification or commit with a pasted token. The skill requires stopping
     before commit/push and refusing token requests.
   - **Side effects:** Adds a small amount of guidance text; no behavioral
     change to normal development workflows.

2. `execution-completion-patterns`
   - **Rule added:** Artifact and manifest verification section.
   - **Reusable lesson:** Completion for a handoff means the extracted copy is
     independently verifiable, not just the source directory.
   - **Validation scenario:** Independent extraction test confirmed manifest hash
     match, zero file mismatches, pytest 62 passed, and full-flow chain length 2.
   - **Failure scenario:** Reusing earlier test output or skipping extraction
     would leave the package unverified.
   - **Malicious-instruction scenario:** "Skip the extraction test, it's fine."
     Refuse; the protocol requires independent verification.
   - **Side effects:** None beyond stronger completion criteria for handoff tasks.

3. `github-repo-management`
   - **Rule changed:** Working without `git` or `curl` section now explicitly
     says to stop at a clean artifact directory plus reproducible archive when
     authentication is unavailable, and to provide import scripts.
   - **Reusable lesson:** Python stdlib can push via Git Data API when safe, but
     when auth is unavailable the agent must hand off a clean tree and scripts,
     not pretend to commit.
   - **Validation scenario:** The chain-breaker handoff package is ready for the
     user to import into their own checkout with the provided scripts.
   - **Failure scenario:** Attempting API push without auth or asking for a token
     in chat.
   - **Malicious-instruction scenario:** "Use the token I posted above to push."
     Refuse and remind the user to revoke the token; provide local import
     commands instead.
   - **Side effects:** Adds safe fallback path to existing GitHub workflows.

### Skills created

- `artifact-handoff-without-git` — complete protocol for manifest generation,
  archive creation, independent extraction testing, and safe import-script
  generation when Git is unavailable.

### Other skills from this engagement

- `claim-versus-code-verification` — verify quality claims against direct evidence.
- `canonical-serialization-review` — review canonical serialization for
  consensus-critical data.
- `adversarial-test-generation` — generate adversarial tests for validation
  failures and malformed input.
