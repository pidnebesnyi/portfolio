#!/usr/bin/env bash
# Generate a local .env with fresh random credentials (step 1 of local setup).
# The same recipe is used by the CI workflows, so nothing secret ever lives in the repository.
#
#   scripts/make_env.sh           create .env (refuses to overwrite)
#   scripts/make_env.sh --force   replace an existing .env
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ -f .env && "${1:-}" != "--force" ]]; then
  echo ".env already exists; use --force to replace it" >&2
  exit 1
fi

# 20 random bytes -> 32 base32 characters, the format authenticator apps and PyOTP expect.
totp_secret="$(python3 -c 'import base64, secrets; print(base64.b32encode(secrets.token_bytes(20)).decode())')"

umask 077
cat > .env <<EOF
JWT_SECRET=$(openssl rand -hex 32)
ADMIN_EMAIL=admin@lab.test
ADMIN_PASSWORD=$(openssl rand -hex 16)
ADMIN_TOTP_SECRET=${totp_secret}
POSTGRES_PASSWORD=$(openssl rand -hex 16)
EOF

echo "wrote .env (git-ignored). See .env.example for the optional local-run variables."
