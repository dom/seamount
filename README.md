# Seamount

### A Stateless Compute Forge for Thermocline-Compliant Task and Job Dispatch

**Version:** 0.4.0
**Status:** RFC — Pre-release, seeking feedback
**License:** MIT
**Implements:** Thermocline 0.4.0+
**Works with:** Photophore 0.3.0+

> **Implementation status.** The shipped reference forges are **task-only**.
> Every section below that is marked **NOT YET IMPLEMENTED (v0.2)** — the job
> execution surface, runtime isolation model, tool registry, and performance
> targets — is normative *intent* for future job-capable forges and has no
> verified implementation in this repo. Do not read those sections as tested
> behavior.

---

## What Is a Forge?

A forge is any Thermocline-compliant node that:

1. Receives a Thermocline task or job envelope
2. Performs the requested work using available runtimes and tools
3. Returns a Thermocline result envelope with a receipt signature
4. Holds no state between sessions

A forge is defined entirely by what it accepts and what it returns — the Thermocline
contract. The hardware underneath, the runtimes installed, the network path used
to reach it — none of these are specified by the contract.

Seamount is the **reference forge implementation**: a local compute server designed
to run on powerful personal hardware — a desktop, a high-end laptop, a local
workstation — and serve as the compute backend for one or more sovereign nodes
running a policy engine (Photophore or equivalent).

---

## Reference Implementations

Two reference forges live in this repo; both satisfy the conformance requirements
below and share no code beyond `thermocline-py` imports — exercising the
"spec, not framework" posture in practice.

| Forge | Task type | Determinism | Receipt attests | Photophore | Live reference |
|---|---|---|---|---|---|
| [`pi-forge/`](./pi-forge/) | `data.compute` (π to N digits) | bit-identical reruns | computed result + integrity | no | https://pi.dom.net |
| [`llm-forge/`](./llm-forge/) | `data.inference.text` (OpenAI-compatible chat completion) | nondeterministic | **relay fidelity** + integrity (NOT inference correctness — see its README) | shadowed mode | BYOK local only |

`llm-forge` is intentionally a weaker verifiability story than `pi-forge`: the
signature commits to faithful relay of the call, not to LLM output correctness.
This caveat is load-bearing — see [`llm-forge/README.md` §"What the signature
does and does not attest"](./llm-forge/README.md).

---

## Design Philosophy

**Stateless by design.** Seamount holds no memory between tasks or jobs. Each
envelope is processed in isolation. When the result is returned — or when a job
halts — Seamount discards everything associated with that task or job.

**Dumb by intent.** Seamount does not make policy decisions, does not classify
content, and does not attempt to infer what it does not need to know. That work
was done by the policy engine before the envelope was sent.

**The forge executes, never interprets.** For job envelopes, Seamount executes
against the sealed manifest. If a step is ambiguous, it halts.

---

## Forge Conformance Requirements (Normative)

This section defines the **universal requirements** any forge MUST satisfy to be
Thermocline-compliant. Reference implementation notes (hardware advice, runtime choices,
examples) are non-normative and appear in Appendix A.

### 1) Envelope Handling

- The forge MUST validate envelope schema and reject malformed envelopes.
- The forge MUST reject unrecognized Thermocline versions (`UNSUPPORTED_VERSION`).
- The forge MUST treat envelope content as untrusted input.

### 2) Signature Verification

- The forge MUST verify `dispatch_signature` before processing any envelope.
- The forge MUST verify signatures using the identity provider interface declared
  by `dispatch_signature.key_scheme`.
- If verification fails, the forge MUST return `SIGNATURE_INVALID` (task) or halt
  `SIGNATURE_INVALID` (job) and MUST NOT execute.

### 3) Privacy Fence / Logging

- The forge MUST NOT persist task/job context, prompts, shadows, abstractions, or
  outputs beyond the lifetime of the request.
- The forge MUST NOT log content. Operational logs may include: envelope_id/job_id,
  timestamps, task types, tool IDs, status codes, and selected runtime identifiers.
- The forge MUST enforce `manifest.constraints.may_access[]` (job envelopes) at the
  tool routing layer. *NOT YET IMPLEMENTED (v0.2): job envelopes are not accepted
  by the shipped task-only forges, so `may_access[]` enforcement has no
  implementation yet.*
- Any attempt to use a tool not in `may_access[]` MUST halt with `PRIVACY_VIOLATION`.
  *NOT YET IMPLEMENTED (v0.2).*

### 4) Statelessness

- The forge MUST NOT persist any task/job input, intermediate value, or output
  beyond the lifetime of the request (no database, no spool files, no history).
- The forge MUST NOT maintain a cross-request cache of prior envelopes, results,
  or intermediate step outputs; each envelope is processed in isolation.
- On success, halt, or failure, the forge MUST release all per-request buffers
  so they become unreachable and eligible for garbage collection before the
  response (or halt result) is returned.
- Zeroization caveat: in managed runtimes with immutable string/bytes types
  (including the reference forges' Python implementation), overwriting freed
  memory cannot be guaranteed; copies of request data may persist in process
  memory until collected and reused. A forge MUST NOT be advertised as
  performing guaranteed memory zeroization unless its runtime can actually
  enforce it. Deployments that need stronger erasure guarantees should rely on
  process-per-request isolation or full-memory-encryption at the platform
  layer.

### 5) Task Execution

- The forge MUST route `task.task.type` to a configured runtime adapter.
- If no runtime exists for a task type, the forge MUST return `TASK_TYPE_UNAVAILABLE`.
- The forge MUST return a structured error envelope (never unstructured stdout).

### 6) Job Execution

> **NOT YET IMPLEMENTED (v0.2).** No shipped forge accepts job envelopes; none
> of the halt codes below (`MANIFEST_TAMPER`, `PASSTHROUGH_VIOLATION`,
> `CONTRACT_MISMATCH`, `STEP_AMBIGUOUS`) is emitted by any code in this repo.
> The conformance harness scores this item as an explicit skip for task-only
> forges.

The forge MUST implement the job integrity rules defined by Thermocline 0.2.0+:

- Manifest Immutability → `MANIFEST_TAMPER`
- Passthrough Containment → `PASSTHROUGH_VIOLATION`
- Output Contract Validation → `CONTRACT_MISMATCH`
- Privacy Fence Enforcement → `PRIVACY_VIOLATION`
- Intermediate State Opacity (no partial outputs transmitted)
- Forge Executes, Never Interprets → `STEP_AMBIGUOUS`

### 7) Receipt Signatures

Every task_result and job_result MUST include a receipt signature.

- The receipt signature MUST cover the entire result envelope.
- The receipt signature MUST include `inputs_received` listing shadow IDs and/or
  identifiers for public blocks actually consumed.
- The forge MUST sign using a key managed by an identity provider (local keystore).

Receipt signature shape:

```json
"receipt_signature": {
  "key_scheme": "brine",
  "node_id": "<forge node id>",
  "envelope_id": "<matches incoming envelope>",
  "inputs_received": ["<shadow_id or public block id>", "..."],
  "timestamp": "<iso8601>",
  "sig": "<signature over result>"
}
```

### 8) Error and Halt Codes

**Task error codes (minimum required):**
- `INVALID_ENVELOPE`
- `UNSUPPORTED_VERSION`
- `SIGNATURE_INVALID`
- `TASK_TYPE_UNAVAILABLE`
- `RUNTIME_ERROR`
- `TIMEOUT`
- `UNKNOWN`

**Job halt codes (minimum required) — NOT YET IMPLEMENTED (v0.2), see §6:**
- `MANIFEST_TAMPER`
- `PASSTHROUGH_VIOLATION`
- `CONTRACT_MISMATCH`
- `STEP_AMBIGUOUS`
- `TOOL_UNAVAILABLE`
- `PRIVACY_VIOLATION`
- `TIMEOUT`
- `SIGNATURE_INVALID`

---

## Supported Task Types (Reference)

Seamount routes incoming tasks to installed runtimes. The routing table is
configured at startup based on what is available on the host machine.

| Task Type | Example Runtimes |
|----------|------------------|
| `text.generate` | Agent runtime, local LLM runtime, cloud provider via API |
| `text.summarize` | Agent runtime, local LLM runtime |
| `text.transform` | Agent runtime, local LLM runtime |
| `image.generate` | Diffusion/ComfyUI runtime |
| `image.describe` | Vision-capable runtime |
| `video.transcribe` | Whisper runtime |
| `audio.transcribe` | Whisper runtime |
| `code.generate` | Code-capable runtime |
| `code.review` | Code-capable runtime |
| `file.process` | Toolchain selected by file type |
| `data.extract` | Structured extraction pipeline |

Custom task types (reverse-domain notation) are supported via plugins.

---

## Tool Registry (Job Envelopes)

> **NOT YET IMPLEMENTED (v0.2).** The shipped forges are task-only and expose
> no tool registry; `TOOL_UNAVAILABLE` is not emitted by any code in this repo.

For `job` envelopes, steps declare a `tool` ID. Seamount maintains a tool registry
mapping tool IDs to local runtime adapters.

If a step declares a tool ID that cannot be resolved at startup, any job that
reaches that step MUST halt with `TOOL_UNAVAILABLE`.

---

## Job Execution Engine

> **NOT YET IMPLEMENTED (v0.2).** This engine does not exist in the shipped
> reference forges; the sequence below is the normative design for future
> job-capable forges.

### Execution Sequence

```
1. Receive job envelope
2. Validate envelope schema and Thermocline version
3. Verify dispatch signature
4. Validate manifest (intent, output_contract, constraints, result_policy present)
5. Resolve all step tool IDs against tool registry — halt TOOL_UNAVAILABLE if any missing
6. For each step (in dependency order):
   a. Validate step input source (manifest or prior step passthrough)
   b. Execute step via resolved tool adapter
   c. Validate output against step's passthrough[] declaration
   d. Hold output in memory for declared passthrough fields only
7. Validate final output against manifest.output_contract
8. Assemble job_result envelope
9. Sign with receipt signature
10. Return job_result to issuer
11. Release all in-memory job state (see §4 Statelessness for what "release"
    guarantees per runtime)
```

Steps with no `depends_on` entries may execute in parallel. Steps with
`depends_on` entries execute only after all declared dependencies complete.

### Halt Behavior

A halted job is a dead job.

On any halt condition, the forge MUST:
1. Stop execution immediately
2. Release all in-memory job state (see §4 Statelessness)
3. Assemble a `job_result` envelope with `status: halted` and `halt_reason`
4. Sign and return the halt result
5. Retain nothing

---

## Runtime Isolation Model (Normative)

> **NOT YET IMPLEMENTED (v0.2).** The reference forges run their single
> in-process runtime at L0 (pure compute / HTTP relay) and expose no `shell`
> tool or plugin system; the isolation levels below are unenforced normative
> intent for job-capable forges.

Seamount may route work to multiple runtimes, some of which are inherently risky
(e.g., `shell`, untrusted plugins). The forge MUST provide isolation boundaries
commensurate with the declared tool.

### Isolation Levels

| Level | Description | Applies to |
|------|-------------|------------|
| L0 | In-process adapter, no sandbox | Pure compute runtimes with no filesystem/network side effects |
| L1 | Process isolation + restricted env | Most local inference runtimes |
| L2 | Process isolation + fs jail + no network | `shell`, converters, glue tooling |
| L3 | Container/VM isolation | Untrusted third-party plugins or remote toolchains |

### Shell Tool Requirements (L2 minimum)

If the forge exposes a `shell` tool ID, it MUST:
- Run commands in a dedicated temporary directory per job (`$JOB_TMPDIR`)
- Provide an allowlisted command set (e.g., ffmpeg, convert, unzip) and deny
  arbitrary binaries by default
- Deny outbound network access
- Deny reading outside `$JOB_TMPDIR` (no access to host filesystem)
- Enforce CPU and wall-clock time limits per step
- Enforce memory ceilings per job
- Ensure cleanup on success, failure, and halt (delete tempdir, zero buffers)

### Plugin Requirements

- Plugins MUST declare capabilities (task types and tool IDs).
- Plugins MUST be probed at startup and marked unavailable if they fail.
- Untrusted plugins SHOULD run at L3 (container/VM). If L0/L1 is used, the forge
  MUST document the risk and treat it as a deployment decision.

---

## Performance Targets (Normative)

> **NOT YET IMPLEMENTED (v0.2).** No shipped forge implements `forge-bench`,
> and none of the budgets below has been measured or verified against the
> reference implementations. Treat this section as unvalidated targets, not
> observed performance.

These are **targets** for forge overhead exclusive of model inference time.
They exist to prevent the security/audit chain from becoming the bottleneck.

### Per-Operation Targets (p50 on modern desktop hardware)

| Operation | Target |
|----------|--------|
| JSON parse + schema validate (task) | < 1 ms |
| JSON parse + schema validate (job) | < 5 ms |
| ed25519 verify dispatch signature | < 0.5 ms |
| ed25519 sign receipt signature | < 0.5 ms |
| SHA-256 hash for audit linkage (if used locally) | < 0.1 ms |
| Tool registry resolution | < 1 ms |

### End-to-End Overhead Targets

| Path | Target |
|------|--------|
| Task (receive→verify→route→result envelope assembly, excluding inference) | < 10 ms |
| Job (receive→verify→manifest validate, excluding step runtime time) | < 25 ms |

### Benchmarking Guidance

A conformant Seamount implementation SHOULD ship with a `forge-bench` mode that:
- Runs schema validation and signing/verification loops (10k iterations)
- Emits p50/p95 timings
- Runs a no-op job with N steps to measure orchestration overhead

---

## Threat Model

Seamount's threat model addresses attacks against the forge: untrusted input,
runtime escape, denial-of-service, impersonation, and side channels.

### Trust Assumptions

| Assumption | Implication |
|------------|------------|
| Incoming envelopes are untrusted | Treat as hostile input; validate strictly |
| The forge host OS is not compromised | If the host is compromised, statelessness and isolation cannot be guaranteed |
| Runtime adapters may be buggy | Isolation is required; do not assume adapters are safe |

### Attack Surfaces and Mitigations

**AT-E1: Malicious Envelope Payloads**
*Attack:* Crafted JSON intended to exploit parser bugs, overflow buffers, or induce
undefined behavior.
*Mitigation:* Use hardened JSON parsing, strict schema validation, size limits
(max envelope bytes), reject unknown fields by default.

**AT-E2: Resource Exhaustion (DoS)**
*Attack:* A job crafted with large step graphs, huge parameters, or tasks that
consume excessive CPU/GPU/memory.
*Mitigation:* Enforce per-envelope size limits, per-job timeouts, per-step timeouts,
maximum step count, maximum artifact size. Return `TIMEOUT` or `RUNTIME_ERROR`.

**AT-E3: Tool Escape / Shell Breakout**
*Attack:* Use `shell` or plugin tools to read host files, exfiltrate secrets, or
open network connections.
*Mitigation:* L2/L3 isolation requirements, deny network, fs jail, allowlist
commands, ephemeral tempdirs, strict environment.

**AT-E4: Forge Impersonation**
*Attack:* A malicious node pretends to be a known forge and returns forged receipt
signatures.
*Mitigation:* The issuer verifies receipt signatures against the registered forge
public key. Registration binds node_id→public_key.

**AT-E5: Timing Side Channels**
*Attack:* Observe job runtime variance to infer sensitive properties (e.g., which
hidden model ran, approximate prompt length if it leaks into runtime).
*Mitigation:* Coarse-grain operational logs, avoid exposing fine-grained timing to
untrusted observers, prefer local transports for sensitive jobs.

### Residual Risks

- A compromised forge host OS breaks isolation.
- A malicious runtime adapter can leak data via covert channels (timing, resource
  usage) even under isolation. This is bounded by what the envelope contains.

---

## Receipt Signature

Every Seamount result envelope includes a receipt signature (see conformance).
Combined with the dispatch signature, this forms the privacy receipt stored in the
issuer audit log.

---

## Configuration (Reference)

Seamount is configured via a single YAML file at startup. Configuration declares:
- Transport (socket path, TCP port, TLS)
- Runtime adapters and backing services
- Task routing table
- Tool registry
- Timeout limits
- Key scheme and key storage location
- Operational log destination

Configuration is static at runtime. Changes require restart.

---

## Architecture Decision Records

Seamount inherits suite-wide ADRs from `thermocline-py`:

- [ADR-0001: Python 3.11 as primary language](../thermocline/docs/adr/ADR-0001-python-3-11-as-primary-language.md)
- [ADR-0003: Single canonical JSON path](../thermocline/docs/adr/ADR-0003-single-canonical-json-path.md)
- [ADR-0005: No in-process key material](../thermocline/docs/adr/ADR-0005-no-in-process-key-material.md)

See [docs/adr/index.md](docs/adr/index.md) for the full index.

---

## Changelog

This is the **spec document** changelog. Implementation releases (reference
forges, conformance harness, CI) are tracked in [CHANGELOG.md](./CHANGELOG.md).

### 0.4.0
- Security hardening release; requires Thermocline 0.4.0+ (`verify_envelope`
  with explicit `allow_unsigned` opt-in; `none`-scheme envelopes rejected by
  default)
- Signature verification (§2) is now the enforced default in all reference
  forges: envelopes with a missing, `none`-downgraded, or tampered
  `dispatch_signature` are rejected with `SIGNATURE_INVALID`
- Statelessness (§4) rewritten to claim only what the runtime can enforce
  (buffer release, no persistence, no cross-request cache; explicit
  zeroization caveat)
- Envelope handling hardened: structured errors for non-object JSON bodies,
  request body size limit (default 1 MiB), non-reflective error envelopes,
  loopback bind by default
- Marked the not-yet-implemented normative surface explicitly: Job Execution
  (§6, halt codes), `may_access[]` privacy-fence enforcement, Tool Registry,
  Job Execution Engine, Runtime Isolation Model, and Performance Targets are
  labeled **NOT YET IMPLEMENTED (v0.2)** so the draft spec cannot be read as
  verified behavior

### 0.3.0
- Added Forge Conformance Requirements (Normative) section — consolidated universal
  forge MUST/SHOULD requirements (validation, signature verify, statelessness,
  privacy fence, job integrity rules, receipt signatures, error/halt codes)
- Added Runtime Isolation Model (Normative) — isolation levels, shell tool minimum
  requirements (fs jail, no network, allowlist), plugin requirements
- Added Performance Targets (Normative targets) — per-operation budgets and end-to-end
  overhead targets excluding inference time; benchmarking guidance
- Added Threat Model section — malicious envelopes, DoS, tool escape, impersonation,
  timing side channels; mitigations and residual risk
- Moved hardware recommendations, Thunderbolt deployment narrative, and naming note
  to Appendix A (non-normative)
- Simplified dependency declarations to Thermocline 0.3.0+ and Photophore 0.3.0+ (minimum versions for full feature set)

### 0.2.0
- Added job execution engine: manifest validation, step runner, passthrough
  enforcement, integrity rule enforcement, halt behavior
- Added tool registry
- Extended statelessness guarantee to cover halt
- Extended receipt signature to cover job_result envelopes

### 0.1.0
- Initial draft release
- Core task envelope receive/return cycle
- Unix socket and TCP transports
- Text inference adapters
- Forge registration handshake
- Structured error envelopes
- Static YAML configuration

---

## Appendix A — Non-Normative

### Recommended Runtime Stack (Apple Silicon)

| Category | Primary | Secondary |
|----------|---------|-----------|
| Text inference | MLX | Ollama |
| Image generation | FLUX/MLX or ComfyUI | Diffusers |
| Transcription | Whisper/MLX | faster-whisper |

### Thunderbolt-Connected Creative Forge

Two personal machines on the same desk connected by Thunderbolt.
The sovereign node authors job manifests; the forge executes them.

### A Note on Naming

A seamount is an isolated underwater mountain — a site of transformation rising from
the ocean floor. Hydrothermal vents on seamounts receive mineral-laden seawater,
run it through pressure and heat, and release the transformed result back into the
water column. Nothing is stored between events. The seamount does not remember what
passed through it. It forges; it does not hold.

A forge should work the same way: receive work, execute it completely, return the
result, hold nothing.

---

*Seamount is maintained as an open community specification and reference
implementation. MIT licensed.*
*Companion projects: Thermocline (envelope spec) · Photophore (shadow protocol)*
