#!/usr/bin/env python3
"""Daily, READ-ONLY search for public developer requests; no auto-messaging.

Unsolicited GitHub comments are not allowed; results are an internal review queue.
"""
import datetime as dt
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

SEARCHES = (
    '"agent automation" in:title is:issue is:open',
    '"evidence verification" in:title is:issue is:open',
    '"workflow audit" in:title is:issue is:open',
)


def search(query):
    params = urlencode({"q": query, "per_page": 10, "sort": "updated", "order": "desc"})
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "agent-economy-lead-radar/1.0"}
    token = os.environ.get("OPPORTUNITY_GITHUB_TOKEN", "")
    if token:
        headers["Authorization"] = "Bearer " + token
    with urlopen(Request("https://api.github.com/search/issues?" + params, headers=headers), timeout=15) as response:
        return json.load(response)


def main():
    findings = {}
    errors = []
    for query in SEARCHES:
        try:
            result = search(query)
            for entry in result.get("items", []):
                url = entry.get("html_url", "")
                if not url.startswith("https://github.com/"):
                    continue
                findings[url] = {"title": entry.get("title", "")[:250], "url": url,
                                 "updated_at": entry.get("updated_at", ""), "state": entry.get("state", "")}
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            errors.append({"query": query, "error": type(exc).__name__})
    payload = {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
               "description": "Public issue discovery for human review, NOT verified leads, customers or consent to solicit.",
               "searches": list(SEARCHES), "candidate_issues": list(findings.values()), "errors": errors}
    output = Path(os.environ.get("OPPORTUNITY_OUT", "opportunity-report.json"))
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Found {len(findings)} public candidate issues (not contacted). Wrote {output}.")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
