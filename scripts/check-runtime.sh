#!/usr/bin/env bash
set -euo pipefail

output="${RUNNER_TEMP:?}/authority-runtime"
mkdir -p "$output"
tmp=$(mktemp -d)
container=
cleanup() {
  if [[ -n "$container" ]]; then docker rm -fv "$container" >/dev/null; fi
  rm -rf "$tmp"
}
trap cleanup EXIT
docker build --iidfile "$tmp/image" --label "org.opencontainers.image.revision=${GITHUB_SHA:?}" .
image=$(cat "$tmp/image")
# The test token lives exclusively inside this disposable container.
container=$(docker run -d --network none --entrypoint sh "$image" -ec '
  umask 077
  export CONTRACT_AUTHORITY_TOKEN_FILE=/tmp/authority-token
  /app/.venv/bin/python -c "import secrets; print(secrets.token_hex(32))" > "$CONTRACT_AUTHORITY_TOKEN_FILE"
  exec /app/.venv/bin/hypermesh-contract-authority
')
for attempt in {1..30}; do
  if docker exec "$container" /app/.venv/bin/python -c '
import json
from urllib.request import Request, urlopen
from pathlib import Path
base = "http://127.0.0.1:8080"
assert json.load(urlopen(base + "/health", timeout=2)) == {"status": "ok"}
token = Path("/tmp/authority-token").read_text().strip()
meta = json.load(urlopen(Request(base + "/v1/meta", headers={"X-Internal-Token": token}), timeout=2))
assert meta["writer"] == "self-use" and meta["financial"] is False
' 2>/dev/null; then break; fi
  if [[ $attempt == 30 ]]; then docker logs "$container"; exit 1; fi
  sleep 1
done
docker save "$image" | gzip -1 > "$output/runtime.tar.gz"
(cd "$output" && sha256sum runtime.tar.gz > SHA256SUMS)
cp "$tmp/image" "$output/image-id"
