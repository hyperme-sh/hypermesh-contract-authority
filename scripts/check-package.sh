#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
project=$PWD
scratch=$(mktemp -d)
trap 'rm -rf "$scratch"' EXIT
uv lock --check
uv export --frozen --no-emit-project --format requirements-txt --output-file "$scratch/requirements.txt" >/dev/null
uv venv --python 3.13 "$scratch/venv"
python="$scratch/venv/bin/python"
uv pip sync --python "$python" "$scratch/requirements.txt"
uv build --out-dir "$scratch/dist"
mkdir "$scratch/run"
cp -R tests "$scratch/run/tests"
cp -R tools "$scratch/run/tools"
check() {
  (cd "$scratch/run" && "$python" -I -m pytest tests -q --junitxml="$scratch/$1.xml")
}
uv pip install --python "$python" --no-deps -e "$project"
check source
uv pip install --python "$python" --no-deps --reinstall "$scratch"/dist/*.whl
check wheel
"$python" - "$scratch" <<'PY'
from pathlib import Path
import sys,tarfile
p=Path(sys.argv[1])
with tarfile.open(next((p/'dist').glob('*.tar.gz'))) as archive:
 archive.extractall(p/'sdist',filter='data')
PY
uv build --wheel "$scratch"/sdist/* --out-dir "$scratch/rebuilt"
uv pip install --python "$python" --no-deps --reinstall "$scratch"/rebuilt/*.whl
check sdist
"$python" - "$scratch" "$project/LICENSE" <<'PY'
from pathlib import Path
from xml.etree import ElementTree as E
from importlib.metadata import distribution
import sys
p=Path(sys.argv[1]); inventories=[]
for form in ['source','wheel','sdist']:
 r=E.parse(p/(form+'.xml')).getroot()
 assert not any(list(r.iter(tag)) for tag in ['failure','error','skipped'])
 inventories.append(sorted((t.get('classname'),t.get('name')) for t in r.iter('testcase')))
assert inventories[0] and inventories[0]==inventories[1]==inventories[2]
d=distribution('hypermesh-contract-authority')
assert d.metadata['License-Expression']=='Apache-2.0'
[license]=[f for f in d.files if str(f).endswith('.dist-info/licenses/LICENSE')]
assert d.locate_file(license).read_bytes()==Path(sys.argv[2]).read_bytes()
print(f'{len(inventories[0])} matching tests per form; exact Apache license verified')
PY
if [[ -n "${EVIDENCE_DIR:-}" ]]; then
 mkdir -p "$EVIDENCE_DIR"
 cp "$scratch"/*.xml "$scratch"/dist/* "$EVIDENCE_DIR/"
fi
