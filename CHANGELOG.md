# Changelog

All notable changes to Seamount are documented here. The format is a lite
variant of [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); semantic
versioning per [SemVer](https://semver.org/spec/v2.0.0.html).

## [0.4.0] - 2026-07-07

Security-hardening release following external review. Requires
**`thermocline-py` >= 0.4.0** (`verify_envelope(..., allow_unsigned=False)`
rejects `none`-scheme envelopes with `UNSIGNED_SCHEME_REJECTED`).

### Security

- **All three forges (`pi-forge`, `llm-forge`, `describe-forge`) require a
  verified brine `dispatch_signature` by default** (HIGH). Envelope content
  can no longer select an unauthenticated path: missing signatures,
  `key_scheme: none` downgrades, unknown signers, and tampered signatures are
  all rejected with `SIGNATURE_INVALID` (HTTP 401). Dev-mode opt-out is the
  explicit `FORGE_REQUIRE_DISPATCH_SIG=0`.
- `llm-forge` receipt signatures now bind to the request (request digest in
  the signed envelope), closing receipt-replay across requests (MED).
- Request body size limit (`FORGE_MAX_CONTENT_LENGTH`, default 1 MiB) with a
  structured 413; error envelopes no longer reflect attacker-controlled
  content (LOW). Resolves the v0.1 "AT-E2 size-limit enforcement deferred"
  known limitation; the AT-E2 `xfail` is retired in favor of live tests.
- Forges bind `127.0.0.1` by default; non-loopback binding is an explicit
  `FORGE_BIND_HOST` opt-in (LOW).
- Structured `MALFORMED_ENVELOPE` errors for non-object JSON bodies instead
  of unstructured 500s (MED).

### Changed

- **Conformance harness is behavioral** (MED): checklist items 1/2/7 can no
  longer silently skip (a required-item skip scores FAIL); item 2 runs three
  live negatives (missing signature, `none` downgrade, self-hosted
  tampered-signature fixture) that must each return `SIGNATURE_INVALID`;
  unknown-task-type and wrong-version cases assert exact error codes; the
  harness signs positive-path fixtures with an ephemeral sovereign key
  (`--sovereign-register-service`). A forge that accepts an unsigned envelope
  now FAILS conformance.
- `conformance/at_negative/` AT-E1/E2/E4 are live behavioral tests against
  real forge subprocesses instead of file-existence checks.
- Statelessness spec text (README §4) scoped to enforceable claims (buffer
  release, no persistence, no cross-request cache) with an explicit
  zeroization caveat.
- Spec doc marks the entire job surface (`may_access[]`, job halt codes,
  tool registry, job execution engine, runtime isolation model) and the
  Performance Targets as **NOT YET IMPLEMENTED (v0.2)**.

### Added

- `llm-forge` CI coverage: unit tests, print lint, and a conformance matrix
  leg driven by `forge_conformance --role llm-forge` against a canned
  OpenAI-compatible mock upstream (`forge_conformance._mock_upstream`).

### Dependencies

- All forge and conformance packages pin `thermocline>=0.4.0`.

## [0.1.0] - 2026-05-13

### Added

- `pi-forge` upgraded from the pre-Phase-3 placeholder to a real Seamount-
  compliant forge: brine ed25519 signing via the platform secure keystore,
  `init` and `serve` subcommands, `PIFORGE_READY port=<n>` readiness marker
  contractual with Photophore's integration-test harness.
- `describe-forge`, a new tier-1-aware forge that accepts shadow envelopes and
  returns templated descriptions. `DESCRIBEFORGE_READY` marker.
- `forge_conformance` cross-suite conformance harness (CONF-01). Validates
  any forge against the 12-item Seamount checklist. Runs against the reference
  forges in CI; can be invoked against third-party impls on demand.
- 5 AT-E* negative tests under `conformance/at_negative/` (CONF-02):
  AT-E1 (malicious payload), AT-E2 (resource exhaustion, xfail v0.1),
  AT-E3 (tool escape), AT-E4 (forge impersonation), AT-E5 (timing side channel).
- `at_coverage.py` per-repo coverage assertion + `ast_lint_no_print.py`
  forbidding `print(` in library code paths (CONF-06).

### Implemented

- **FORGE-01..05.** Forge bootstrap, brine signing, receipt issuance,
  tier-1 shadow handling (describe-forge), conformance harness integration.
- **Suite-wide CONF-01..08.** Seamount contributes its slice of the
  suite-wide conformance requirements (FORGE-* surface + AT-E* negative tests).

### Spec dependencies

- Requires **`thermocline-py` 0.3.1** for the SP-3.3-01..03 envelope-signature
  invariants. See `thermocline/README.md` §"Identity Provider Interface"
  §"Dispatch Signatures" + §"Receipt Signatures" and
  `thermocline/CHANGELOG.md` §[0.3.1]. Both reference forges sign receipts
  with the `receipt_signature.sig=""` (empty string, not removed)
  canonicalization shape and emit the `sig` field (verifiers MAY accept
  either `sig` or `bytes_hex` for compatibility with pre-0.3.1 drafts).
  These invariants were co-discovered while integrating the forges with the
  reference dispatch coordinator, then promoted to spec-level after we
  confirmed any third-party implementation would otherwise reverse-engineer
  the Python coordinator to discover them.

### Deferred to subsequent milestones

- Job envelopes + per-step forge invocation (Seamount spec v0.2)
- Multi-step manifests (v0.2)
- Per-forge resource limits (v0.2, AT-E2 size-limit enforcement)
- Sandboxed forge runtimes (v0.2)
- Third-party forge certification badge (post-v0.1)

### Known limitations

- **`mypy --strict` on forges deferred to v0.2.** Both `pi-forge` (20 errors)
  and `describe-forge` (17 errors) exceeded the pre-v0.1 audit's >3-error
  auto-fix budget. v0.1 ships with non-strict mypy on both forges (ruff +
  pytest are the primary type guards). Re-enable by uncommenting
  `strict = true` in each forge's `pyproject.toml [tool.mypy]` section.
  Annotation work needed: predominantly missing dict/list type-args in
  `envelope.py` helpers and missing return annotations on Flask route
  handlers. Also requires `types-mpmath` or `# type: ignore[import-untyped]`
  for the `mpmath` and `flask` modules.
- **AT-E2 size-limit enforcement** deferred to v0.2. v0.1 forges have no
  upper bound on the `digits` parameter; production deployments should
  proxy through a size-limiting reverse proxy until size limits ship at the
  forge layer. `test_at_e2_resource_exhaustion` is marked `xfail`.
- **AT-A5 trust-store tamper-detector** deferred to v0.2 (concern is
  photophore-side, but cross-referenced here for completeness). v0.1
  defense is the three-store separation enforced by CHAN-04 + ADR-0001;
  explicit on-read tamper detection is a v0.2 strengthening.
- Default `python-keyring` macOS Keychain entries are software-backed
  (encrypted at rest, gated by user's login session). Hardware-anchored
  Apple Silicon Secure Enclave entries require a developer signing identity;
  deferred to v0.2. v0.1 threat model is satisfied without Secure Enclave:
  key material never leaves the keystore.
- Linux + Windows ops paths documented best-effort; CI-tested matrix only
  covers `macos-latest` (forge unit tests + conformance) and `ubuntu-latest`
  (lint + AT-coverage).
