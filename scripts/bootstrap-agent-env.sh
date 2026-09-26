#!/usr/bin/env bash
# Materialize gitignored local credential files from Cloud Agent environment
# secrets (or the current shell). Never commit the generated files.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

require_or_warn() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    echo "bootstrap-agent-env: missing ${name} (set as a Cloud Agent environment secret)" >&2
    return 1
  fi
}

missing=0
require_or_warn AWS_ACCESS_KEY_ID || missing=1
require_or_warn AWS_SECRET_ACCESS_KEY || missing=1
require_or_warn EC_API_KEY || missing=1
if [[ "${missing}" -ne 0 ]]; then
  echo "bootstrap-agent-env: skipping credential file write" >&2
  exit 0
fi

AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-eu-west-1}"

write_env_aws() {
  local dest="$1"
  mkdir -p "$(dirname "${dest}")"
  umask 077
  cat >"${dest}" <<EOF
export AWS_ACCESS_KEY_ID='${AWS_ACCESS_KEY_ID}'
export AWS_SECRET_ACCESS_KEY='${AWS_SECRET_ACCESS_KEY}'
export AWS_DEFAULT_REGION='${AWS_DEFAULT_REGION}'
export EC_API_KEY='${EC_API_KEY}'
EOF
  chmod 600 "${dest}"
  echo "bootstrap-agent-env: wrote ${dest}"
}

# AWS example (primary PoC path)
write_env_aws "${ROOT}/examples/aws/.env.aws"

# Optional copies for other cloud examples when those dirs exist
[[ -d "${ROOT}/examples/gcp" ]] && write_env_aws "${ROOT}/examples/gcp/.env.aws"
[[ -d "${ROOT}/examples/azure" ]] && write_env_aws "${ROOT}/examples/azure/.env.aws"
[[ -d "${ROOT}/examples/multicloud" ]] && write_env_aws "${ROOT}/examples/multicloud/.env.aws"

# Convenience: ensure terraform can see AWS creds via the default chain too
mkdir -p "${HOME}/.aws"
umask 077
cat >"${HOME}/.aws/credentials" <<EOF
[default]
aws_access_key_id = ${AWS_ACCESS_KEY_ID}
aws_secret_access_key = ${AWS_SECRET_ACCESS_KEY}
EOF
cat >"${HOME}/.aws/config" <<EOF
[default]
region = ${AWS_DEFAULT_REGION}
EOF
chmod 600 "${HOME}/.aws/credentials" "${HOME}/.aws/config"
echo "bootstrap-agent-env: wrote ~/.aws/credentials"
