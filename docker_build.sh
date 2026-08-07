#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_VERSION="$(python3 - <<'PY' "$SCRIPT_DIR/app/settings.py"
import re
import sys
from pathlib import Path

content = Path(sys.argv[1]).read_text()
match = re.search(r'app_version = os\.getenv\("APP_VERSION", "([^"]+)"\)', content)
if not match:
    raise SystemExit("Could not detect current APP_VERSION default")
print(match.group(1))
PY
)"

read -r -p "Version [$DEFAULT_VERSION]: " VERSION
VERSION="${VERSION:-$DEFAULT_VERSION}"

if [[ ! "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "Invalid version '$VERSION'. Expected format: X.Y.Z" >&2
    exit 1
fi

python3 - <<'PY' "$SCRIPT_DIR" "$VERSION"
import re
import sys
from pathlib import Path

root = Path(sys.argv[1])
version = sys.argv[2]

targets = {
    root / "app/settings.py": (
        r'app_version = os\.getenv\("APP_VERSION", "[^"]+"\)',
        f'app_version = os.getenv("APP_VERSION", "{version}")',
    ),
    root / "README.md": (
        r'\| `APP_VERSION` \| `[^`]+` \|',
        f'| `APP_VERSION` | `{version}` |',
    ),
}

for path, (pattern, replacement) in targets.items():
    content = path.read_text()
    updated, count = re.subn(pattern, replacement, content, count=1)
    if count != 1:
        raise SystemExit(f"Could not update version in {path}")
    path.write_text(updated)
PY

docker compose build
docker tag csv-cups-app-app:latest harbor.somenergia.coop/erp/csv-cups-app:latest
docker tag csv-cups-app-app:latest "harbor.somenergia.coop/erp/csv-cups-app:${VERSION}"
docker push harbor.somenergia.coop/erp/csv-cups-app:latest
docker push "harbor.somenergia.coop/erp/csv-cups-app:${VERSION}"
