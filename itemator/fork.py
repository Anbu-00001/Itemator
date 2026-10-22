"""Write a fork's copies of the two flows and the CI job with its own account names: `python -m itemator.fork --group my-group --out fork`.

GitLab names each flow's service account after the flow and the top-level group (`ai-itemator-card-<group>`,
`ai-itemator-react-<group>`). This project's files name its own two accounts in three places: the reaction flow's
prompt, and the `variables:` entry and the `export` line of ci/itemator-job.yml. This writes copies with the new names
and prints the steps a person still does in GitLab. It changes no file of this repository. Standard library only."""
from __future__ import annotations

import argparse
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CARD, REACT = "ai-itemator-card-gitlab-ai-hackathon", "ai-itemator-react-gitlab-ai-hackathon"
FILES = {"flows/itemator_card.yml": 0, "flows/itemator_react.yml": 2, "ci/itemator-job.yml": 2}   # how many names each holds
NAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,254}")     # a GitLab username; a name goes into a model prompt, so nothing else


def copies(card: str, react: str) -> dict[str, str]:
    """{path: text} with this project's two account names replaced; SystemExit on a name that is not a username,
    or when a file no longer holds the names it is known to hold (so a copy never keeps one of ours unnoticed)."""
    for n in (card, react):
        if not NAME.fullmatch(n):
            raise SystemExit(f"itemator.fork: {n!r} is not a GitLab username")
    if card == react:
        raise SystemExit("itemator.fork: the card and the reaction account must differ")
    out = {}
    for path, count in FILES.items():
        text = (ROOT / path).read_text(encoding="utf-8")
        found = text.count(CARD) + text.count(REACT)
        if found != count:
            raise SystemExit(f"itemator.fork: {path} names the accounts {found} times, expected {count}; not writing")
        out[path] = text.replace(CARD, card).replace(REACT, react)
    return out


def steps(card: str, react: str) -> str:
    return "\n".join([
        "Then, in GitLab (docs/setup.md has each step):",
        "1. Copy itemator/ and ci/itemator-job.yml from this folder into your repository, or into your policy project for the job.",
        "2. AI > Flows: create two private flows from flows/itemator_card.yml and flows/itemator_react.yml, and enable both.",
        f"3. Manage > Members: check that the accounts {card} and {react} exist. If GitLab named them differently, run this again with --card-bot and --react-bot.",
        "4. AI > Triggers: card flow on Pipeline and Assign reviewer; reaction flow on Mention and Merge request ready.",
        f"5. Settings > CI/CD > Variables: ITEMATOR_REACT_BOT = {react} (read by the decision-log job only).",
        "6. Settings > Merge requests: turn on All threads must be resolved.",
    ])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="itemator.fork", description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("--group", help="your top-level group's path; gives the default account names")
    ap.add_argument("--card-bot", help="the card flow's account name, if GitLab named it differently")
    ap.add_argument("--react-bot", help="the reaction flow's account name, if GitLab named it differently")
    ap.add_argument("--out", default="fork", help="folder to write the copies into (default: fork)")
    a = ap.parse_args(argv)
    if not a.group and not (a.card_bot and a.react_bot):
        ap.error("give --group, or both --card-bot and --react-bot")
    card = a.card_bot or f"ai-itemator-card-{a.group}"
    react = a.react_bot or f"ai-itemator-react-{a.group}"
    files = copies(card, react)
    out = pathlib.Path(a.out)
    for path, text in files.items():
        (out / path).parent.mkdir(parents=True, exist_ok=True)
        (out / path).write_text(text, encoding="utf-8")
        print(f"wrote {out / path}")
    print(steps(card, react))
    return 0


if __name__ == "__main__":
    sys.exit(main())
