import argparse

from .core import slug


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="textkit")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("slug")
    s.add_argument("text")
    a = ap.parse_args(argv)
    if a.cmd == "slug":
        print(slug(a.text))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
