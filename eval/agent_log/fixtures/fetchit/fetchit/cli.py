import argparse
import json
import sys

from .client import FetchError, fetch_json


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="fetchit")
    ap.add_argument("url")
    ap.add_argument("--timeout", type=float, default=10.0)
    a = ap.parse_args(argv)
    try:
        data = fetch_json(a.url, timeout=a.timeout)
    except FetchError as e:
        print(e, file=sys.stderr)
        return 1
    print(json.dumps(data, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
