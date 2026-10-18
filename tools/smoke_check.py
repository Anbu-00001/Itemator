#!/usr/bin/env python3
"""Fetch each URL until it answers 200 or the time is up; exit 1 and say which one did not. Standard library only.
usage: python3 tools/smoke_check.py URL [URL ...]    (env SMOKE_TRIES, SMOKE_WAIT seconds between tries)"""
import os
import sys
import time
import urllib.request


def fetch(url: str) -> int:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "itemator-smoke"}), timeout=20) as r:
            return r.status
    except Exception as e:                      # noqa: BLE001 -- any failure is "not served yet"
        return getattr(e, "code", 0)


def main(urls: list[str], tries: int, wait: float, sleep=time.sleep, get=fetch) -> int:
    bad = []
    for url in urls:
        for i in range(tries):
            status = get(url)
            if status == 200:
                print(f"ok {url}")
                break
            print(f"try {i + 1} of {tries}: {url} answered {status}")
            if i + 1 < tries:
                sleep(wait)
        else:
            bad.append(url)
    for url in bad:
        print(f"NOT SERVED: {url}", file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: smoke_check.py URL [URL ...]")
    sys.exit(main(sys.argv[1:], int(os.environ.get("SMOKE_TRIES", "12")), float(os.environ.get("SMOKE_WAIT", "10"))))
