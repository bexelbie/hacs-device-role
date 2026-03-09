#!/usr/bin/env bash
# ABOUTME: Local runner for E2E tests against a real HA Docker container.
# ABOUTME: Pulls the HA image, runs pytest with the e2e marker, cleans up.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Configurable via environment
HA_E2E_IMAGE="${HA_E2E_IMAGE:-ghcr.io/home-assistant/home-assistant:stable}"
HA_E2E_PORT="${HA_E2E_PORT:-18123}"

echo "=== E2E Test Runner ==="
echo "HA image: $HA_E2E_IMAGE"
echo "HA port:  $HA_E2E_PORT"
echo ""

# Ensure Docker is available
if ! command -v docker &> /dev/null; then
    echo "ERROR: docker is not installed or not in PATH"
    exit 1
fi

# Pull the image (skip if already present)
echo "Pulling HA image (if needed)..."
docker pull "$HA_E2E_IMAGE" 2>/dev/null || true

# Clean up any leftover container from a previous run
docker rm -f ha-e2e-test 2>/dev/null || true

# Run the E2E tests
echo "Running E2E tests..."
cd "$REPO_ROOT"

export HA_E2E_IMAGE HA_E2E_PORT

# Activate venv if present
if [ -f "venv/bin/activate" ]; then
    # shellcheck disable=SC1091
    source venv/bin/activate
fi

pytest tests/e2e/ -v -m e2e --tb=short --confcutdir=tests/e2e
exit_code=$?

# Clean up container regardless of test result
echo "Cleaning up..."
docker rm -f ha-e2e-test 2>/dev/null || true

exit $exit_code
