#!/usr/bin/env bash
# Generate protobuf bindings for C++, Go, Python, and TypeScript.
# Run from repo root: bash tools/codegen/codegen.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PROTO_DIR="$ROOT/packages/schemas/proto"
OUT_ROOT="$ROOT/packages/schemas/gen"

mkdir -p "$OUT_ROOT"/{cpp,go,python,ts}

PROTOS=()
while IFS= read -r f; do PROTOS+=("$f"); done < <(find "$PROTO_DIR" -name '*.proto' | sort)

echo "Generating from ${#PROTOS[@]} .proto files..."

# Need protoc on PATH.
if ! command -v protoc >/dev/null 2>&1; then
  echo "error: protoc not installed. Run: brew install protobuf" >&2
  exit 1
fi

# C++
protoc -I "$PROTO_DIR" \
  --cpp_out="$OUT_ROOT/cpp" \
  "${PROTOS[@]}"

# Python
protoc -I "$PROTO_DIR" \
  --python_out="$OUT_ROOT/python" \
  --pyi_out="$OUT_ROOT/python" \
  "${PROTOS[@]}"

# Go (skips silently if protoc-gen-go absent — Go service isn't built yet).
if command -v protoc-gen-go >/dev/null 2>&1; then
  protoc -I "$PROTO_DIR" \
    --go_out="$OUT_ROOT/go" \
    --go_opt=paths=source_relative \
    "${PROTOS[@]}"
fi

# TypeScript via ts-proto if available.
if [ -x "$ROOT/node_modules/.bin/protoc-gen-ts_proto" ]; then
  protoc -I "$PROTO_DIR" \
    --plugin="$ROOT/node_modules/.bin/protoc-gen-ts_proto" \
    --ts_proto_out="$OUT_ROOT/ts" \
    --ts_proto_opt=esModuleInterop=true,outputServices=none \
    "${PROTOS[@]}"
fi

echo "Done. Generated bindings under $OUT_ROOT"
