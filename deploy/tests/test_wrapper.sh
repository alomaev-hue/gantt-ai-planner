#!/usr/bin/env bash
# deploy/tests/test_wrapper.sh
#
# Exercises planner-deploy-wrapper's SSH_ORIGINAL_COMMAND validation.
# 'sudo' is stubbed via PATH so nothing privileged ever runs, and the real
# planner-deploy is never invoked. Nothing here touches a real server.
#
# Usage: bash deploy/tests/test_wrapper.sh
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
wrapper="$script_dir/../planner-deploy-wrapper"
stub_dir="$(mktemp -d)"
log_file="$stub_dir/sudo.log"

cleanup() { rm -rf "$stub_dir"; }
trap cleanup EXIT

cat > "$stub_dir/sudo" <<'EOF'
#!/usr/bin/env bash
echo "sudo $*" >> "$(dirname "$0")/sudo.log"
exit 0
EOF
chmod +x "$stub_dir/sudo"

pass=0
fail=0

run_case() {
    desc="$1"
    input="$2"
    expect_status="$3"
    expect_log_substr="${4:-}"

    : > "$log_file"
    set +e
    SSH_ORIGINAL_COMMAND="$input" PATH="$stub_dir:$PATH" "$wrapper" >/dev/null 2>&1
    status=$?
    set -e

    if [ "$status" -ne "$expect_status" ]; then
        echo "FAIL: $desc (expected exit $expect_status, got $status)"
        fail=$((fail + 1))
        return
    fi

    if [ -n "$expect_log_substr" ]; then
        if ! grep -qF "$expect_log_substr" "$log_file"; then
            echo "FAIL: $desc (expected sudo call containing: $expect_log_substr)"
            fail=$((fail + 1))
            return
        fi
    elif [ -s "$log_file" ]; then
        echo "FAIL: $desc (expected sudo NOT to be called, but it was: $(cat "$log_file"))"
        fail=$((fail + 1))
        return
    fi

    echo "PASS: $desc"
    pass=$((pass + 1))
}

run_case "valid short sha tag" \
    "sha-abc1234" 0 "sudo /usr/local/bin/planner-deploy sha-abc1234"
run_case "valid full-length sha tag" \
    "sha-0123456789abcdef0123456789abcdef01234567" 0 \
    "sudo /usr/local/bin/planner-deploy sha-0123456789abcdef0123456789abcdef01234567"
run_case "empty command rejected" "" 1
run_case "wrong prefix rejected" "latest" 1
run_case "hex too short rejected" "sha-abc12" 1
run_case "uppercase hex rejected" "sha-ABC1234" 1
run_case "extra token rejected" "sha-abc1234 extra" 1
run_case "shell metacharacters rejected" "sha-abc1234; rm -rf /" 1
# Single-quoted on purpose: we want the literal string passed through,
# not expanded by this test script's own shell.
# shellcheck disable=SC2016
run_case "command substitution rejected" '$(rm -rf /)' 1

echo
echo "test_wrapper.sh: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
