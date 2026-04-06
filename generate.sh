#!/usr/bin/env bash
# T: SDK Codegen — fetches the OpenAPI spec from a running server and prints
# a summary of all operations.  Can be extended to auto-generate client stubs.
#
# Usage:
#   ./sdk/generate.sh [BASE_URL]
#
# Default BASE_URL: http://127.0.0.1:8099

set -euo pipefail

BASE_URL="${1:-http://127.0.0.1:8099}"
SPEC_URL="${BASE_URL}/api/v1/openapi.json"

echo "=== CivitasOS SDK Codegen ==="
echo "Fetching OpenAPI spec from ${SPEC_URL} ..."

SPEC=$(curl -sf "${SPEC_URL}" 2>/dev/null) || {
    echo "ERROR: Cannot reach ${SPEC_URL}"
    echo "Start the backend first: cd civitasos-backend && cargo run"
    exit 1
}

TITLE=$(echo "$SPEC" | python3 -c "import sys,json; print(json.load(sys.stdin)['info']['title'])" 2>/dev/null || echo "CivitasOS")
VERSION=$(echo "$SPEC" | python3 -c "import sys,json; print(json.load(sys.stdin)['info']['version'])" 2>/dev/null || echo "unknown")

echo ""
echo "API: ${TITLE} v${VERSION}"
echo ""
echo "Operations:"
echo "─────────────────────────────────────────────"

echo "$SPEC" | python3 -c "
import sys, json

spec = json.load(sys.stdin)
paths = spec.get('paths', {})
count = 0
for path, methods in sorted(paths.items()):
    for method, detail in sorted(methods.items()):
        if method in ('get','post','put','delete','patch'):
            op_id = detail.get('operationId', '-')
            summary = detail.get('summary', '')
            print(f'  {method.upper():6s} {path:45s} {op_id:30s} {summary}')
            count += 1
print(f'\nTotal: {count} operations')
"

echo ""
echo "SDK files:"
echo "  Python:     sdk/python/civitasos_client.py"
echo "  TypeScript: sdk/typescript/civitasos-client.ts"
echo ""
echo "Done."
