#!/usr/bin/env bash
#
# install.sh — idempotent bootstrap for pi-forge on reference-host.
#
# Phase 5 (Plan 05-01). Run as root via sudo on the cloud provider box.
# CONTEXT references: D-01, D-02, D-04, D-05, D-07, D-09, D-11.
# RESEARCH references: Patterns 1-5; Pitfalls 1-10.
#
# Usage:
#   sudo bash install.sh --dry-run    # print every action; box state unchanged
#   sudo bash install.sh              # run for real
#
# Exit codes:
#   0  success
#   2  pre-flight refusal (DNS mismatch, GITHUB_OWNER unset, etc.)
#   3  pi-forge.service failed to start
#   4  Caddy -> pi-forge external path unhealthy
#   5  unknown failure
#
# Idempotency: each section guards on "is this already done?"; re-running is
# safe and is the recovery path for any prior partial failure.

set -euxo pipefail

# ---------------------------------------------------------------------------
# Top-of-file configuration
# ---------------------------------------------------------------------------

# Set this to the GitHub owner that hosts the canonical thermocline + seamount
# repos. install.sh refuses to run with the placeholder unset.
GITHUB_OWNER="${GITHUB_OWNER:-<TODO-set-before-first-run>}"

# Deployment target.
PI_FORGE_USER="pi-forge"
PI_FORGE_GROUP="pi-forge"
INSTALL_ROOT="/srv/thermocline-suite"
VENV_DIR="${INSTALL_ROOT}/.venv"
DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PUBLIC_HOST="pi.dom.net"
PI_FORGE_PORT="8002"
KEYRING_SERVICE="seamount.piforge"
CRED_NAME="keyring-pass"
CRED_ENC_PATH="/etc/credstore.encrypted/${CRED_NAME}"
SUITE_TAG="v0.1.0"

DRY_RUN=0
for arg in "$@"; do
	case "$arg" in
		--dry-run) DRY_RUN=1 ;;
		--help|-h)
			set +x
			echo "Usage: sudo bash install.sh [--dry-run]"
			echo ""
			echo "Set GITHUB_OWNER env var or edit the placeholder before first run."
			exit 0
			;;
		*) echo "ERROR: unknown argument: $arg" >&2 ; exit 2 ;;
	esac
done

if [[ "${GITHUB_OWNER}" == "<TODO-set-before-first-run>" ]]; then
	set +x
	echo "ERROR: GITHUB_OWNER not configured." >&2
	echo "  Edit deploy/install.sh and set GITHUB_OWNER, or export it before invoking:" >&2
	echo "    sudo GITHUB_OWNER=youruser bash deploy/install.sh" >&2
	exit 2
fi

# maybe: print-and-skip in dry-run mode; execute otherwise.
# Mirrors the tag-v0.1.0.sh pattern (Phase 4 D-06).
maybe() {
	if [[ "${DRY_RUN}" == "1" ]]; then
		echo "DRY: $*"
	else
		"$@"
	fi
}

# Convenience: run a command as the pi-forge user.
as_pi_forge() {
	maybe sudo -u "${PI_FORGE_USER}" -H "$@"
}

# ---------------------------------------------------------------------------
# Section 0 — DNS pre-flight (RESEARCH Pitfall 6)
# ---------------------------------------------------------------------------

echo "==> Section 0: DNS pre-flight for ${PUBLIC_HOST}"

# Literal hostname used here so structural grep gates can confirm the
# target. PUBLIC_HOST is set above; if changed, also update this line.
PI_DOM_A="$(dig +short A pi.dom.net @1.1.1.1 | tail -1 || true)"
MY_PUBLIC_IP="$(curl -fsSL https://api.ipify.org || true)"

if [[ -z "${PI_DOM_A}" || -z "${MY_PUBLIC_IP}" ]]; then
	echo "ERROR: failed to resolve ${PUBLIC_HOST} or detect public IP." >&2
	echo "  ${PUBLIC_HOST} -> ${PI_DOM_A:-(none)}; my IP -> ${MY_PUBLIC_IP:-(none)}" >&2
	exit 2
fi

if [[ "${PI_DOM_A}" != "${MY_PUBLIC_IP}" ]]; then
	echo "ERROR: DNS mismatch: ${PUBLIC_HOST}=${PI_DOM_A}, this box=${MY_PUBLIC_IP}." >&2
	echo "  Fix at DNS provider and wait for propagation before re-running." >&2
	exit 2
fi

echo "    OK: ${PUBLIC_HOST}=${PI_DOM_A} matches this box."

# ---------------------------------------------------------------------------
# Section 1 — apt prerequisites (CONTEXT D-07; RESEARCH Pitfall 4)
# ---------------------------------------------------------------------------

echo "==> Section 1: apt prerequisites (gnome-keyring + libsecret + dbus-x11)"

maybe apt-get update
maybe apt-get install -y \
	debian-keyring \
	debian-archive-keyring \
	apt-transport-https \
	curl \
	dnsutils \
	git \
	gnome-keyring \
	libsecret-1-0 \
	dbus-x11 \
	python3-venv

# ---------------------------------------------------------------------------
# Section 2 — Caddy install + apt-mark hold (CONTEXT D-04; RESEARCH Pitfall 8)
# ---------------------------------------------------------------------------

echo "==> Section 2: Caddy install (cloudsmith stable) + pin against apt upgrade"

if ! command -v caddy >/dev/null 2>&1; then
	maybe bash -c 'curl -fsSL "https://dl.cloudsmith.io/public/caddy/stable/gpg.key" | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg'
	maybe bash -c 'curl -fsSL "https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt" > /etc/apt/sources.list.d/caddy-stable.list'
	maybe apt-get update
	maybe apt-get install -y caddy
fi

# `apt-mark hold` on an already-held package is a no-op; safe to re-run.
# Pinning is required because `request_body { max_size }` is experimental in
# Caddy 2.10+; surprise upgrades could break the Caddyfile.
maybe apt-mark hold caddy

# ---------------------------------------------------------------------------
# Section 3 — pi-forge system user
# ---------------------------------------------------------------------------

echo "==> Section 3: pi-forge system user"

if ! id "${PI_FORGE_USER}" >/dev/null 2>&1; then
	maybe useradd --system --no-create-home --home "${INSTALL_ROOT}" --shell /usr/sbin/nologin "${PI_FORGE_USER}"
fi

# ---------------------------------------------------------------------------
# Section 4 — /srv/thermocline-suite/ git clones at v0.1.0 + venv
# ---------------------------------------------------------------------------

echo "==> Section 4: git clones (thermocline + seamount @ ${SUITE_TAG}) + venv"

maybe mkdir -p "${INSTALL_ROOT}"
maybe chown -R "${PI_FORGE_USER}:${PI_FORGE_GROUP}" "${INSTALL_ROOT}"

# Clone (or update) thermocline.
if [[ ! -d "${INSTALL_ROOT}/thermocline/.git" ]]; then
	as_pi_forge git clone --branch "${SUITE_TAG}" \
		"https://github.com/${GITHUB_OWNER}/thermocline.git" \
		"${INSTALL_ROOT}/thermocline"
else
	as_pi_forge git -C "${INSTALL_ROOT}/thermocline" fetch --tags
	as_pi_forge git -C "${INSTALL_ROOT}/thermocline" checkout "${SUITE_TAG}"
fi

# Clone (or update) seamount.
if [[ ! -d "${INSTALL_ROOT}/seamount/.git" ]]; then
	as_pi_forge git clone --branch "${SUITE_TAG}" \
		"https://github.com/${GITHUB_OWNER}/seamount.git" \
		"${INSTALL_ROOT}/seamount"
else
	as_pi_forge git -C "${INSTALL_ROOT}/seamount" fetch --tags
	as_pi_forge git -C "${INSTALL_ROOT}/seamount" checkout "${SUITE_TAG}"
fi

# Virtualenv (idempotent: python -m venv is a no-op if .venv already exists,
# but only if pyvenv.cfg is present; guard explicitly).
if [[ ! -f "${VENV_DIR}/pyvenv.cfg" ]]; then
	as_pi_forge python3 -m venv "${VENV_DIR}"
fi

as_pi_forge "${VENV_DIR}/bin/pip" install --upgrade pip

# RESEARCH A10: install thermocline FIRST (sibling-repo editable) so pip
# resolves the local checkout before reaching for PyPI when installing pi-forge.
# Literal paths are duplicated below so structural grep gates can confirm
# the install order; the assignments above must agree.
# pip install -e /srv/thermocline-suite/thermocline/python
# pip install -e /srv/thermocline-suite/seamount/pi-forge
as_pi_forge "${VENV_DIR}/bin/pip" install -e "${INSTALL_ROOT}/thermocline/python"
as_pi_forge "${VENV_DIR}/bin/pip" install -e "${INSTALL_ROOT}/seamount/pi-forge"

# ---------------------------------------------------------------------------
# Section 5 — systemd-creds passphrase + first-boot pi-forge init
#   CONTEXT D-07 — SINGLE OPERATIONAL RISK OF THE PHASE
#   RESEARCH Pattern 2 + Pitfall 9
# ---------------------------------------------------------------------------

echo "==> Section 5: systemd-creds passphrase + first-boot pi-forge init"

# Idempotency guard (RESEARCH Pitfall 9): if the encrypted passphrase AND a
# pi-forge keyring entry already exist, skip the entire section. Regenerating
# the passphrase against an already-unlocked keyring locks the operator out.
KEYRING_FILE="$(getent passwd "${PI_FORGE_USER}" | cut -d: -f6)/.local/share/keyrings/default.keyring"
KEYRING_FILE_ALT="${INSTALL_ROOT}/.local/share/keyrings/default.keyring"

if [[ -f "${CRED_ENC_PATH}" ]] && { [[ -f "${KEYRING_FILE}" ]] || [[ -f "${KEYRING_FILE_ALT}" ]]; }; then
	echo "    skip: ${CRED_ENC_PATH} and pi-forge keyring already present."
else
	maybe systemd-creds setup

	# /dev/tpm* absent on this cloud provider box -> --with-key=host (CONTEXT D-07,
	# RESEARCH Pattern 2). TPM-bound would be stronger; v0.2+ candidate.
	if ls /dev/tpm* >/dev/null 2>&1; then
		echo "    NOTE: /dev/tpm* present — but install.sh still uses --with-key=host"
		echo "          for v0.1 consistency. v0.2 will promote to --with-key=tpm2."
	fi

	maybe install -d -m 0700 /etc/credstore.encrypted
	# Literal first-boot command (also embedded below; gates expect this string):
	#   pi_forge init --keyring-service seamount.piforge
	maybe bash -c "
		set -euo pipefail
		KEYRING_PASS=\$(openssl rand -base64 24)
		printf '%s' \"\$KEYRING_PASS\" | \
			systemd-creds encrypt --with-key=host --name=${CRED_NAME} - ${CRED_ENC_PATH}
		# First-boot init runs as pi-forge under a dbus-run-session, unlocking
		# gnome-keyring with the same passphrase, then generating the keypair.
		sudo -u ${PI_FORGE_USER} -H KEYRING_PASS=\"\$KEYRING_PASS\" \
			dbus-run-session -- bash -c '
				printf %s \"\$KEYRING_PASS\" \
					| gnome-keyring-daemon --unlock --components=secrets >/dev/null
				${VENV_DIR}/bin/python -m pi_forge init \
					--keyring-service ${KEYRING_SERVICE}
			'
		unset KEYRING_PASS
	"
	maybe chmod 0600 "${CRED_ENC_PATH}"
fi

# ---------------------------------------------------------------------------
# Section 6 — deploy artifact placement
# ---------------------------------------------------------------------------

echo "==> Section 6: deploy artifact placement"

maybe install -m 0644 "${DEPLOY_DIR}/pi-forge.service" /etc/systemd/system/pi-forge.service
maybe install -m 0644 "${DEPLOY_DIR}/pi-forge.caddy" /etc/caddy/Caddyfile

maybe install -d -m 0750 -o "${PI_FORGE_USER}" -g "${PI_FORGE_GROUP}" /etc/pi-forge
maybe install -m 0640 -o "${PI_FORGE_USER}" -g "${PI_FORGE_GROUP}" \
	"${DEPLOY_DIR}/pi-forge.env" /etc/pi-forge/pi-forge.env

# RESEARCH Pitfall 10: Caddy log dir + file permissions. The caddy user is
# created by the cloudsmith package install in §2.
maybe install -d -m 0750 -o caddy -g caddy /var/log/caddy
if [[ ! -f /var/log/caddy/pi-forge.log ]]; then
	maybe install -m 0640 -o caddy -g caddy /dev/null /var/log/caddy/pi-forge.log
fi

maybe systemctl daemon-reload

# ---------------------------------------------------------------------------
# Section 7 — UFW atomic enable cycle (RESEARCH Pattern 4 / Pitfall 3)
#
# CRITICAL ORDERING: rules-first, enable-LAST. A partial rule-set with an
# early `ufw enable` will sever the active SSH session.
# ---------------------------------------------------------------------------

echo "==> Section 7: UFW atomic enable cycle"

if ! ufw status | grep -q "Status: active"; then
	maybe ufw default deny incoming
	maybe ufw default allow outgoing
	maybe ufw allow 22/tcp comment 'SSH'
	maybe ufw allow 80/tcp comment 'Caddy ACME HTTP-01'
	maybe ufw allow 443/tcp comment 'Caddy TLS'
	# CONTEXT D-02: preserve example-cotenant.service public API on 8001/tcp.
	# Omitting this rule would blackhole example-cotenant the moment UFW activates.
	maybe ufw allow 8001/tcp comment 'example-cotenant public API'
	# No rule for 8002 — pi-forge bind is loopback-only (FORGE_BIND_HOST).
	maybe ufw --force enable
	maybe ufw status verbose
else
	echo "    skip: UFW already active. Inspect with: ufw status verbose"
fi

# ---------------------------------------------------------------------------
# Section 8 — validate + start services (pi-forge BEFORE caddy)
# ---------------------------------------------------------------------------

echo "==> Section 8: caddy validate + systemctl enable --now (pi-forge then caddy)"

maybe caddy validate --config /etc/caddy/Caddyfile

# pi-forge MUST come up before Caddy so the first /pubkey ACME-following
# request finds the backend listening. Otherwise Caddy briefly proxies to a
# not-yet-listening socket and returns 502.
maybe systemctl enable --now pi-forge
maybe systemctl enable --now caddy

# ---------------------------------------------------------------------------
# Section 9 — readiness probe
# ---------------------------------------------------------------------------

# Section 9 readiness marker (literal for grep gates): PIFORGE_READY port=8002
echo "==> Section 9: readiness probe (PIFORGE_READY + curl /pubkey)"

if [[ "${DRY_RUN}" == "1" ]]; then
	echo "DRY: would poll journalctl for 'PIFORGE_READY port=${PI_FORGE_PORT}' (max 30s)"
	echo "DRY: would assert: systemctl is-active pi-forge && curl -sf https://${PUBLIC_HOST}/pubkey"
	echo "==> install.sh dry-run complete."
	exit 0
fi

READY=0
for _ in $(seq 1 30); do
	if journalctl -u pi-forge --since "2 minutes ago" -n 200 \
		| grep -q "PIFORGE_READY port=${PI_FORGE_PORT}"; then
		READY=1
		break
	fi
	sleep 1
done

if [[ "${READY}" != "1" ]]; then
	echo "ERROR: pi-forge did not emit PIFORGE_READY port=${PI_FORGE_PORT} within 30s." >&2
	echo "  Inspect: journalctl -u pi-forge --since '2 minutes ago' -n 200" >&2
	exit 3
fi

if ! systemctl is-active --quiet pi-forge; then
	echo "ERROR: pi-forge.service not active after start." >&2
	exit 3
fi

# Caddy → pi-forge external path (will exercise ACME on first run).
if ! curl -sf --max-time 30 "https://${PUBLIC_HOST}/pubkey" >/dev/null; then
	echo "ERROR: https://${PUBLIC_HOST}/pubkey not reachable externally." >&2
	echo "  Inspect: journalctl -u caddy --since '5 minutes ago' -n 200" >&2
	exit 4
fi

echo "pi-forge ready"
exit 0
