#!/usr/bin/env bash
# Configure the local AWS CLI default profile to assume the TF3 readonly role.
set -euo pipefail

ROLE_ARN="arn:aws:iam::197826770971:role/tf3-production-readonly"
BASE_PROFILE="tf3-member-base"
REGION="ap-southeast-1"

usage() {
  cat <<'EOF'
Usage:
  scripts/setup-readonly-aws-profile.sh <name-readonly>

Example:
  scripts/setup-readonly-aws-profile.sh tutruong-readonly

Before running, use "aws configure" with the member IAM user's access key.
The session name must end with "-readonly" for audit clarity.
EOF
}

if [[ $# -ne 1 ]]; then
  usage
  exit 2
fi

SESSION_NAME="$1"
if [[ ! "$SESSION_NAME" =~ ^[A-Za-z0-9+=,.@_-]+-readonly$ ]]; then
  echo "ERROR: session name must use AWS STS-safe characters and end with '-readonly'." >&2
  echo "Example: tutruong-readonly" >&2
  exit 2
fi

AWS_DIR="${HOME}/.aws"
CREDENTIALS_FILE="${AWS_DIR}/credentials"
CONFIG_FILE="${AWS_DIR}/config"
STAMP="$(date +%Y%m%d%H%M%S)"

mkdir -p "$AWS_DIR"

if [[ ! -f "$CREDENTIALS_FILE" ]]; then
  echo "ERROR: $CREDENTIALS_FILE not found. Run 'aws configure' first with the member IAM user key." >&2
  exit 1
fi

cp "$CREDENTIALS_FILE" "${CREDENTIALS_FILE}.bak.${STAMP}"
[[ -f "$CONFIG_FILE" ]] && cp "$CONFIG_FILE" "${CONFIG_FILE}.bak.${STAMP}"

python3 - "$CREDENTIALS_FILE" "$CONFIG_FILE" "$BASE_PROFILE" "$ROLE_ARN" "$REGION" "$SESSION_NAME" <<'PY'
import configparser
import pathlib
import sys

credentials_path = pathlib.Path(sys.argv[1])
config_path = pathlib.Path(sys.argv[2])
base_profile = sys.argv[3]
role_arn = sys.argv[4]
region = sys.argv[5]
session_name = sys.argv[6]

credentials = configparser.RawConfigParser()
credentials.optionxform = str
credentials.read(credentials_path)

if credentials.has_section("default"):
    if not credentials.has_section(base_profile):
        credentials.add_section(base_profile)
        for key, value in credentials.items("default"):
            credentials.set(base_profile, key, value)
    credentials.remove_section("default")

if not credentials.has_section(base_profile):
    raise SystemExit(
        f"ERROR: no [{base_profile}] credentials found. Run 'aws configure' first, "
        "or put the member IAM access key under [tf3-member-base]."
    )

with credentials_path.open("w") as f:
    credentials.write(f)

config = configparser.RawConfigParser()
config.optionxform = str
config.read(config_path)

if not config.has_section("default"):
    config.add_section("default")

config.set("default", "role_arn", role_arn)
config.set("default", "source_profile", base_profile)
config.set("default", "role_session_name", session_name)
config.set("default", "region", region)
config.set("default", "output", "json")

with config_path.open("w") as f:
    config.write(f)
PY

echo "Configured default AWS profile to assume:"
echo "  $ROLE_ARN"
echo "Session name:"
echo "  $SESSION_NAME"
echo
echo "Verify:"
echo "  aws sts get-caller-identity"
echo
echo "Expected ARN:"
echo "  arn:aws:sts::197826770971:assumed-role/tf3-production-readonly/${SESSION_NAME}"
