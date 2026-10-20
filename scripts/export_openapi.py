#!/usr/bin/env python3
"""Pin the running service's OpenAPI document as the contract the suite checks against.

    python scripts/export_openapi.py [BASE_URL]      # default http://127.0.0.1:8000

Writes tests/contract/openapi.json. Run it only when an API change is intended, and commit the
file with that change: the diff of the pinned document is how the change gets reviewed.
"""

import json
import sys
import urllib.request
from pathlib import Path

PINNED = Path(__file__).resolve().parent.parent / "tests" / "contract" / "openapi.json"


def main() -> None:
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
    if not base_url.startswith(("http://", "https://")):
        sys.exit(f"not an http(s) URL: {base_url}")
    url = f"{base_url.rstrip('/')}/openapi.json"
    with urllib.request.urlopen(url, timeout=10) as response:  # noqa: S310 - scheme checked above
        spec = json.load(response)
    PINNED.write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {PINNED}")  # noqa: T201 - command-line output


if __name__ == "__main__":
    main()
