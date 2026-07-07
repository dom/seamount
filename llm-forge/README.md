# llm-forge — Thermocline-compliant relay forge for OpenAI-compatible inference

`llm-forge` is the second reference implementation in the Thermocline suite.
It accepts a Thermocline task envelope, forwards the inference call to any
OpenAI-Chat-Completions-compatible endpoint (0G Private Computer, OpenAI,
OpenRouter, vLLM, local stacks), and returns a brine-signed `task_result`
envelope around the response.

It exists to prove three things:

1. **The envelope schema generalizes** beyond `pi-forge`'s deterministic
   compute to nondeterministic external inference, with zero changes to
   `thermocline-py` or the spec.
2. **The `IdentityProvider` / brine / canonicalize stack is reusable as-is.**
   `llm-forge` shares no code with `pi-forge` other than what's imported
   from `thermocline-py`.
3. **Photophore shadows compose with forges.** `llm-forge`'s shadowed mode
   is the first non-photophore-internal consumer of the public shadow API.

## What the signature does and does not attest

**The brine signature on a `llm-forge` task_result attests:**

- **Relay fidelity** — "I, this specific forge identity, forwarded the
  caller's `task.parameters.messages` to the configured upstream provider
  and received the verbatim response now recorded in `outputs.response`
  (or in `outputs.response_shadow` in shadowed mode)."
- **Request binding** — `outputs.request_digest` is a SHA-256 over the
  canonical JSON of the relayed request (`model`, `messages`, `max_tokens`,
  `temperature`, `privacy_mode`). Because the digest sits inside the signed
  envelope, the signature links this response to this exact request; a
  signed response cannot be replayed as the answer to a different question.
  Verifiers recompute the digest from the request they dispatched
  (`tests/test_request_binding.py`). Caveat: the digest is deterministic and
  unsalted so the caller can verify offline, which means anyone holding the
  receipt can CONFIRM a guessed prompt against it. In shadowed deployments
  treat the receipt itself as sensitive.
- **Receipt integrity** — "The envelope's `outputs` and `provenance` were
  not modified after I signed it. Any change invalidates the signature."
- **In `privacy_mode: shadowed` only**, additionally: "Neither the prompt
  text nor the response text appears in the canonical bytes I signed."
  (`outputs.request_digest` is a hash of the prompt, not the prompt; see
  the confirmation caveat above.) Enforced structurally by
  `tests/test_shadow_mode.py`.

**The signature does NOT attest:**

- **LLM output correctness.** LLMs are nondeterministic at temperature > 0
  and only ~deterministic at temperature 0 (and even then provider-side
  caching, batching, or model updates can vary). The forge does not re-run,
  replay, compare, or evaluate.
- **Provider trustworthiness.** If the upstream provider returns an
  attacker-substituted or hallucinated response, the forge cannot tell. It
  signs what it received over the wire.
- **TEE attestation.** When `LLM_FORGE_ATTESTATION_JSON` is set, the forge
  records the provider's attestation claim verbatim in
  `outputs.provider_attestation` as opaque data. It does NOT verify the
  attestation. Clients verify those independently against the provider's
  published trust root.
- **Reproducibility.** Unlike `pi-forge`, where re-running the task
  produces bit-identical output, `llm-forge` makes no reproducibility
  claim. The envelope is a per-call artifact, not a verifiable computation.

If you need verified-correctness inference, `llm-forge` plus an off-chain
verifier is not enough. You need a TEE-attested provider whose attestation
your client verifies, or a deterministic-then-attested pipeline. `llm-forge`
gives you a uniform wire-level receipt around the relay step.

## Wire shape

| Endpoint | Method | Purpose |
|---|---|---|
| `/pubkey` | GET | brine pubkey + identity + key_scheme (TOFU pin) |
| `/health` | GET | status + thermocline_version + configured provider label |
| `/task` | POST | signed inference envelope |
| `/models` | GET | operator-configured catalog (from `LLM_FORGE_MODELS_JSON`) |

**Accepted task type:** `data.inference.text`.

**Request `task.parameters`:**

| Field | Type | Required | Description |
|---|---|---|---|
| `model` | string | yes | Model name forwarded to provider |
| `messages` | list[{role, content}] | yes | OpenAI Chat Completions message list |
| `max_tokens` | int | no | Forwarded to provider |
| `temperature` | float | no | Forwarded to provider |
| `privacy_mode` | `"verbatim"` \| `"shadowed"` | no (default `verbatim`) | See below |

**Auth (BYOK):** the caller's HTTP request must carry
`Authorization: Bearer <provider-api-key>`. The forge forwards the header
verbatim to the upstream provider and never persists it.
`tests/test_relay_fidelity.py::test_byok_key_not_persisted_anywhere`
asserts the key does not appear anywhere in the signed envelope.

**Response `outputs` (verbatim mode):** `response`, `request_digest`,
`model`, `finish_reason`, `tokens_in`, `tokens_out`, `provider`,
`provider_request_id`, optional `provider_attestation`.

**Response `outputs` (shadowed mode):** `prompt_shadow` and
`response_shadow` replace `response`; the prompt text is not echoed back.
Each shadow is a `{shadow_id, content_type, abstraction, relevance}`
dict — see `photophore.shadow.Shadow`.

## Run it (BYOK, local)

```bash
# 1. Set up a venv with the suite installed editable.
cd seamount/llm-forge
uv venv --python 3.11
uv pip install -e ../../thermocline/thermocline/python -e ../../photophore/python -e .

# 2. Generate the forge keypair (idempotent).
LLMFORGE_KEYRING_SERVICE=seamount.llmforge.local \
  ./.venv/bin/python -m llm_forge init

# 3. Serve against 0G Private Computer.
LLM_FORGE_BASE_URL=https://pc.0g.ai/api/v1 \
  LLM_FORGE_PROVIDER_LABEL=0g-pc \
  LLMFORGE_KEYRING_SERVICE=seamount.llmforge.local \
  ./.venv/bin/python -m llm_forge serve --port 5101 &

# 4. End-to-end verify (post + verify signature against pinned pubkey).
LLM_FORGE_PROVIDER_KEY=<your-0g-key> \
  ./.venv/bin/python examples/verify.py \
  http://127.0.0.1:5101 examples/task-summarize-0g.json

# 5. Same fixture against OpenAI — proves provider-agnostic.
LLM_FORGE_BASE_URL=https://api.openai.com/v1 \
  LLM_FORGE_PROVIDER_LABEL=openai \
  LLMFORGE_KEYRING_SERVICE=seamount.llmforge.local \
  ./.venv/bin/python -m llm_forge serve --port 5102 &
LLM_FORGE_PROVIDER_KEY=<your-openai-key> \
  ./.venv/bin/python examples/verify.py \
  http://127.0.0.1:5102 examples/task-summarize-openai.json

# 6. Shadowed mode — visually confirm outputs.response is absent.
LLM_FORGE_PROVIDER_KEY=<your-0g-key> \
  ./.venv/bin/python examples/verify.py \
  http://127.0.0.1:5101 examples/task-shadowed.json
```

## Env vars

| Var | Default | Purpose |
|---|---|---|
| `FORGE_NODE_ID` | `llm-forge-local` | Responder field in receipts |
| `FORGE_KEY_SCHEME` | `brine` | `none` disables signing (dev only) |
| `FORGE_PORT` | `5101` | (pi-forge uses 5100 — co-tenant-safe) |
| `FORGE_BIND_HOST` | `127.0.0.1` | Set to `0.0.0.0` for non-loopback (use a reverse proxy) |
| `LLMFORGE_KEYRING_SERVICE` | `seamount.llmforge` | libsecret namespace |
| `LLMFORGE_IDENTITY` | `llm-forge` | keystore-entry name |
| `LLM_FORGE_BASE_URL` | (unset) | e.g. `https://pc.0g.ai/api/v1` |
| `LLM_FORGE_PROVIDER_LABEL` | `unknown` | Recorded as `outputs.provider` |
| `LLM_FORGE_MODELS_JSON` | `[]` | Catalog returned by `/models` |
| `LLM_FORGE_ATTESTATION_JSON` | (unset) | Static `outputs.provider_attestation` payload |

## Verification (what every test exercises)

```bash
./.venv/bin/python -m pytest tests/ -v
```

| Test | Asserts |
|---|---|
| `test_pubkey_endpoint.py` | `/pubkey` shape, 503 when no keypair, `/health` shape |
| `test_envelope_shape.py` | Signed receipt parses via `thermocline.envelope.TaskResult.parse_strict`; unsupported task type rejected; missing Bearer auth returns 401 |
| `test_provider_protocol.py` | OpenAI Chat Completions wire shape; upstream 4xx propagates; optional params omitted when unset |
| `test_relay_fidelity.py` | Messages forwarded verbatim; response carried verbatim into envelope; BYOK key never appears in receipt |
| `test_shadow_mode.py` | **Load-bearing privacy** — no 8+ char prompt or response substring in canonical signed bytes; verbatim-mode negative control proves the test is non-trivial |

## How this constrains the suite

- **BYOK is the auth model for v0.1.** Future metered/paid llm-forge is new ground.
- **No streaming.** `data.inference.stream` is unsolved (sign chunks?
  sign final concat? both?) and is a separate spike.
- **OpenAI-compatible only.** Anthropic Messages API and Cohere have
  different shapes; adding them widens the `LLMProvider` Protocol.
- **Photophore becomes a hard dependency for relay forges.** Photophore's
  API stability is now load-bearing beyond its own repo.
- **Receipt verifiability is weaker than `pi-forge`'s.** This is the most
  important caveat. See §"What the signature does and does not attest".
- **"OpenAI-body-compatible" is not the same as "OpenAI-auth-compatible".**
  `OpenAICompatibleProvider` assumes Bearer-token auth in the `Authorization`
  header. Providers whose auth is browser-session or wallet-based (e.g.,
  the in-browser SDK at `pc.0g.ai`) need a different adapter even though
  their request/response bodies match.

## A note on 0G Private Computer specifically

0G PC speaks the OpenAI Chat Completions request/response shape but routes
through `https://router-api.0g.ai/v1` (NOT `pc.0g.ai/api/v1` — that's the
dashboard, whose in-browser SDK uses Privy session cookies rather than
Bearer tokens). External clients use a Bearer-token API key issued via the
0G dashboard at `https://pc.0g.ai/sdk/dashboard`.

Calls are settled on-chain against the calling account's 0G balance: a
402 `payment_error / insufficient_balance` from `router-api.0g.ai` means
the account behind the API key has no funds. Top up via the 0G dashboard
before the round-trip can complete. The forge's response in that case is
a structured `task_error` envelope with `code: UPSTREAM_PROVIDER_ERROR`
that quotes 0G's verbatim error — the relay-fidelity contract holds even
on the error path.

## Relationship to `pi-forge`

| Aspect | pi-forge | llm-forge |
|---|---|---|
| Task | `data.compute` (π to N digits) | `data.inference.text` (chat completion) |
| Determinism | bit-identical reruns | nondeterministic |
| Signature attests | per-task computed result + integrity | relay fidelity + integrity |
| Reproducible | yes | no |
| Photophore | no dependency | shadowed mode depends on it |
| Live reference | https://pi.dom.net | not deployed publicly (BYOK local only) |

Both forges share zero code beyond `thermocline-py` imports — the suite's
spec-not-framework posture is intentional and exercised by having two
implementations.
