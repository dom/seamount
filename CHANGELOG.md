# Changelog

All notable changes to Seamount are documented here. The format is a lite
variant of [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); semantic
versioning per [SemVer](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-05-12

### Added

- `pi-forge` upgraded from the pre-Phase-3 placeholder to a real Seamount-
  compliant forge: brine ed25519 signing via the platform secure keystore,
  `init` and `serve` subcommands, `PIFORGE_READY port=<n>` readiness marker
  contractual with Photophore's integration-test harness.
- `describe-forge` — new tier-1-aware forge that accepts shadow envelopes and
  returns templated descriptions. `DESCRIBEFORGE_READY` marker.
- `forge_conformance` cross-suite conformance harness (CONF-01). Validates
  any forge against the 12-item Seamount checklist. Runs against the reference
  forges in CI; can be invoked against third-party impls on demand.
- 5 AT-E* negative tests under `conformance/at_negative/` (CONF-02):
  AT-E1 (malicious payload), AT-E2 (resource exhaustion — xfail v0.1),
  AT-E3 (tool escape), AT-E4 (forge impersonation), AT-E5 (timing side channel).
- `at_coverage.py` per-repo coverage assertion + `ast_lint_no_print.py`
  forbidding `print(` in library code paths (CONF-06).

### Implemented

- **FORGE-01..05** — Forge bootstrap, brine signing, receipt issuance,
  tier-1 shadow handling (describe-forge), conformance harness integration.
- **Suite-wide CONF-01..08** — Seamount contributes its slice of the
  suite-wide conformance requirements (FORGE-* surface + AT-E* negative tests).

### Deferred to subsequent milestones

- Job envelopes + per-step forge invocation (Seamount spec v0.2)
- Multi-step manifests (v0.2)
- Per-forge resource limits (v0.2 — AT-E2 size-limit enforcement)
- Sandboxed forge runtimes (v0.2)
- Third-party forge certification badge (post-v0.1)

### Known limitations

- **`mypy --strict` on forges deferred to v0.2.** Both `pi-forge` (20 errors)
  and `describe-forge` (17 errors) exceeded Plan 04-01 Task 5's >3-error
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
