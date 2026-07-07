# Deploying pi-forge as a public reference forge

This directory ships the operational surface for running `pi-forge v0.1.0` as
a publicly reachable reference deployment. The reference instance maintained
by the Thermocline authors is at **https://pi.dom.net**; the same artifacts
deploy any compliant `pi-forge` instance behind any DNS name. No code in
`pi-forge` or `thermocline-py` changes. This is operational delivery.

## Prerequisites

1. **SSH + sudo** on a fresh Ubuntu 24.04 host with a public IPv4 (and
   optionally IPv6) address.
2. **DNS already pointing at the host.** The public hostname you intend
   to serve (e.g. `pi.example.net`) must resolve to the host's public IPv4
   (A) and IPv6 (AAAA) before `install.sh` runs Caddy. `install.sh §0`
   refuses to proceed on mismatch. ACME HTTP-01 on port 80 will fail
   otherwise. Update the `PUBLIC_HOST` constant at the top of `install.sh`
   to your hostname before first run.
3. **`GITHUB_OWNER` substituted** in `install.sh` (top of file) so it can
   clone the canonical `thermocline` + `seamount` repos. The placeholder
   `<TODO-set-before-first-run>` triggers exit 2.
4. **A clean SSH session** that you intend to keep open until UFW activates
   (Section 7 enables the firewall; an orphaned session sees the new rules
   immediately).
5. **GitHub deploy keys staged** (only while `dom/thermocline` and
   `dom/seamount` are private repos; this prereq becomes a no-op once they
   are public). Generate one ed25519 keypair per repo on the box, register
   each public key as a **read-only** deploy key on its respective repo,
   and place the private keys at:
   - `/etc/pi-forge-deploy-key-thermocline` (root-owned `0600`)
   - `/etc/pi-forge-deploy-key-seamount` (root-owned `0600`)

   GitHub policy refuses the same pubkey as a deploy key on multiple repos;
   two keypairs are required. `install.sh § Section 4a` reads from these
   paths (override with `DEPLOY_KEY_{THERMOCLINE,SEAMOUNT}` env vars),
   stages them under `/srv/thermocline-suite/.ssh/` for the `pi-forge` user,
   and configures git URL rewriting so the existing HTTPS clone URLs route
   over SSH via per-repo host aliases. If both keys are absent the section
   no-ops (public-repo path). If exactly one is present, install.sh refuses
   with exit 2 to avoid asymmetric auth.

## What this deploys

Five artifacts in this directory are installed onto the box:

| Artifact | Installed at | Provided by |
|---|---|---|
| `pi-forge.service` | `/etc/systemd/system/pi-forge.service` | hardened systemd unit (`dbus-run-session` + `LoadCredentialEncrypted`) |
| `pi-forge.caddy` | `/etc/caddy/Caddyfile` | single-site fresh-install Caddyfile (replace the `pi.dom.net` placeholder with your `PUBLIC_HOST`) |
| `pi-forge.env` | `/etc/pi-forge/pi-forge.env` | `FORGE_*` env contract (pins `FORGE_BIND_HOST=127.0.0.1`) |
| `install.sh` | run from `/tmp` | idempotent installer (9 sections, `--dry-run` aware) |
| `README.md` | this file | operator one-pager |

Plus box-side state created by `install.sh`:

- `pi-forge` system user (no shell, no home expansion).
- `/srv/thermocline-suite/{thermocline,seamount}` git clones at `v0.1.0`.
- `/srv/thermocline-suite/.venv` with editable installs of both packages.
- `/etc/credstore.encrypted/keyring-pass` (systemd-creds, `--with-key=host`).
- UFW active with rules for **22, 80, 443** only (no rule for 8002 because
  pi-forge is loopback-only via `FORGE_BIND_HOST=127.0.0.1`). If you are
  co-tenanting another public service on this host, add its port to §7 of
  `install.sh` before running.
- Caddy installed from cloudsmith stable and `apt-mark hold`-ed.

## What this does NOT deploy or change

- **No observability** beyond `/health` and `journalctl`. No Prometheus,
  no Loki, no log shipping. Standard Caddy / systemd journal patterns
  apply if you want them.
- **No in-forge payload-size limit.** Caddy's
  `request_body { max_size 16KB }` on `/task` is the v0.1 backstop. AT-E2
  (resource-exhaustion) enforcement at the forge layer is a v0.2 item.
- **No CI deploy automation.** `install.sh` is invoked manually over SSH
  by an operator. Deliberate: deployment is a trust-significant event.

## Install procedure

From the operator's laptop:

```bash
# Push the 5 artifacts to a branch the box can clone.
cd ~/Projects/dom/seamount
git status   # confirm pi-forge/deploy/ files are committed
git push origin <deploy-branch>
```

On the host (`ssh <user>@<your-deploy-host>`):

```bash
sudo apt update && sudo apt install -y git
cd /tmp && git clone --branch <deploy-branch> https://github.com/<owner>/seamount.git

# Dry-run first — prints every action with DRY: prefix; box state unchanged.
sudo GITHUB_OWNER=<owner> bash /tmp/seamount/pi-forge/deploy/install.sh --dry-run

# Real run. KEEP THE SSH SESSION OPEN until UFW Section 7 confirms green.
sudo GITHUB_OWNER=<owner> bash /tmp/seamount/pi-forge/deploy/install.sh
```

If `install.sh` aborts non-zero at any section, re-run it: idempotent guards
skip already-completed work and the first failed section is the one to debug.

## Verification

Run from a clean laptop (NOT from the box). All five steps should pass.

```bash
# Step 1 — pubkey shape (must-have truth #1).
curl -sf https://${PUBLIC_HOST}/pubkey \
	| jq 'if (.key_scheme == "brine" and .identity == "pi-forge"
	         and (.pubkey | length) == 64)
	      then "OK" else error("malformed: \(.)") end'

# Step 2 — health.
curl -sf https://${PUBLIC_HOST}/health \
	| jq 'if (.status == "ok" and .forge == "pi-forge")
	      then "OK" else error("malformed: \(.)") end'

# Step 3 — signed task result.
curl -sf -X POST https://${PUBLIC_HOST}/task \
	-H 'content-type: application/json' \
	--data @/path/to/seamount/pi-forge/examples/task-100-digits.json \
	| jq 'if (.receipt_signature.sig != null
	          and .task_result.outputs.digits_computed == 100)
	      then "OK" else error("malformed: \(.)") end'

# Step 4 — loopback bind verification.
nmap -p 8002 ${PUBLIC_HOST}
# Expect: 8002/tcp closed or filtered (pi-forge bind is loopback-only via
# FORGE_BIND_HOST=127.0.0.1; Caddy reverse-proxies the public traffic).

# Step 5 — restart + reboot survival (run via SSH on the host).
sudo systemctl restart pi-forge && sleep 5 \
	&& curl -sf https://${PUBLIC_HOST}/pubkey >/dev/null \
	&& echo "restart survived"
sudo reboot
# After SSH reconnects:
curl -sf https://${PUBLIC_HOST}/pubkey >/dev/null && echo "reboot survived"
```

After Step 1 succeeds and Step 4 confirms 8002 closed, commit the BLAKE3
fingerprint to `seamount/pi-forge/README.md § Live Reference Deployment`:

```bash
HEX_PUBKEY=$(curl -sf https://${PUBLIC_HOST}/pubkey | jq -r .pubkey)
FP=$(printf '%s' "$HEX_PUBKEY" | xxd -r -p | b3sum | awk '{print $1}')
echo "blake3:$FP"
```

## Rollback / recovery

Full uninstall path.

```bash
sudo systemctl disable --now pi-forge caddy
sudo apt-mark unhold caddy
sudo apt purge -y caddy
sudo rm -rf /etc/caddy /etc/systemd/system/pi-forge.service /etc/pi-forge
sudo rm -f  /etc/credstore.encrypted/keyring-pass
sudo systemctl daemon-reload
# /srv/thermocline-suite/ left in place for inspection; remove if desired:
# sudo rm -rf /srv/thermocline-suite
# UFW left active; remove the pi-forge-related rules manually if uninstalling
# the firewall as well.
```

Tag-pinned rollback (keep the deployment alive but revert to a prior tag):

```bash
sudo -u pi-forge git -C /srv/thermocline-suite/seamount fetch --tags
sudo -u pi-forge git -C /srv/thermocline-suite/seamount checkout v0.1.0-prev-sha
sudo systemctl restart pi-forge
```

## Troubleshooting

| Section | Warning sign | Fix |
|---|---|---|
| 0 (DNS) | `ERROR: DNS mismatch` | Update A/AAAA at DNS provider; wait for propagation; re-run. |
| 1 (apt) | `gnome-keyring-daemon` missing afterwards | Re-run apt-get install; confirm `/usr/bin/gnome-keyring-daemon` exists. |
| 2 (Caddy) | apt repo signature error | Re-fetch `gpg.key`; confirm `/usr/share/keyrings/caddy-stable-archive-keyring.gpg` is present. |
| 4 (clones) | `fatal: could not read Username for 'https://github.com'` | Set `GITHUB_OWNER` and confirm the repos are public (or pre-authenticate). |
| 5 (keyring) | `gnome-keyring-daemon: error: locked` | Section 5's idempotency guard fired but keyring is locked from a prior partial install. Wipe `~pi-forge/.local/share/keyrings/` AND `/etc/credstore.encrypted/keyring-pass`, then re-run. |
| 5 (TPM) | `/dev/tpm*` warning | Informational only on hosts without TPM — `--with-key=host` is the operational floor. |
| 7 (UFW) | SSH disconnected mid-install | Recover via your cloud provider's serial / web console; run `ufw disable` to roll back; re-run `install.sh`. Always confirm `ufw status verbose` before disconnecting. |
| 8 (Caddy) | `429 Too Many Requests` from Let's Encrypt | ACME rate-limited; wait ≥1h before retrying. DNS pre-flight should have prevented this; if it fires anyway, your DNS may be intermittent. |
| 9 (probe) | Readiness timeout | `journalctl -u pi-forge --since "2 minutes ago" -n 200`; the keyring unlock chain is the typical culprit. |
| Verification Step 4 | `8002/tcp open` externally | `FORGE_BIND_HOST` not honored. Confirm `/etc/pi-forge/pi-forge.env` contains `FORGE_BIND_HOST=127.0.0.1` and `systemctl restart pi-forge`. |

## Known constraints

- **`request_body { max_size }` is experimental in Caddy 2.10+.** install.sh
  §2 `apt-mark hold caddy` pins against surprise upgrades; revisit when
  Caddy 3.x lands.
- **`--with-key=host`, not TPM.** On hosts without `/dev/tpm*`,
  `systemd-creds` falls back to host-key encryption. TPM-bound passphrase
  is a v0.2+ candidate; the v0.1 baseline trades some defense in depth for
  portability across cloud providers that may not expose a TPM.
- **`MemoryDenyWriteExecute=true` commented out** in the systemd unit.
  PyNaCl's libsodium loader may break under that flag; enable empirically
  and curl-test before promoting permanent.

## Known upstream nits

- **Resolved (0.4.0): `server.py` now defaults to `127.0.0.1`.** Binding
  `0.0.0.0` requires an explicit `FORGE_BIND_HOST` opt-in. The systemd
  `FORGE_BIND_HOST=127.0.0.1` line below is now redundant but kept as an
  explicit statement of intent.
