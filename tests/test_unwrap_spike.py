"""The pure parts of eval/unwrap_cases.py and eval/unwrap_spike.py."""
import pathlib, shutil, sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "eval"))
import unwrap_cases as C  # noqa: E402
import unwrap_spike as S  # noqa: E402
from itemator import unwrap as U  # noqa: E402


def test_pick_is_a_fixed_order_independent_of_input_order():
    rows = [(i, i, "A", f"u{i}") for i in range(1, 40)]
    a = C.pick(rows, 12)
    assert [c["pr_id"] for c in a] == [c["pr_id"] for c in C.pick(list(reversed(rows)), 12)]
    assert len(a) == 12 and a[0]["pr_id"] == min(rows, key=lambda r: C.order_key(r[0]))[0] and set(a[0]) == {"pr_id", "number", "agent", "html_url"}


def test_the_seed_is_not_the_other_spikes_seed():
    import hashlib
    assert C.SEED == 20261018 and C.order_key(5) == hashlib.sha256(b"20261018|5").hexdigest()      # the other spike uses 20261017


def test_agreement_with_file():
    assert S.agrees("png", "image/png") and not S.agrees("png", "image/jpeg") and not S.agrees("png", "text/plain")
    assert S.agrees("zip", "application/java-archive") and S.agrees("zip", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    assert not S.agrees("zip", "application/vnd.openxmlformatsXofficedocument")
    assert S.agrees("text", "text/plain") and S.agrees("text", "application/json") and not S.agrees("text", "textual/x")
    assert S.agrees("elf", "application/x-sharedlib") and not S.agrees("elf", "application/x-mach-binary")
    assert not S.agrees("png", "image/png-extra") and not S.agrees("elf", "application/x-sharedlibx") and not S.agrees("png", "xx image/png")
    assert S.agrees("empty", "inode/x-empty") and not S.agrees("nothing", "text/plain")
    assert S.agrees("script", "text/x-script.python") and S.agrees("script", "text/x-shellscript")


def test_verdicts():
    assert S.verdict("png", "image/png") == "agree"
    assert S.verdict("unknown_binary", "application/octet-stream") == "both_generic"
    assert S.verdict("unknown_binary", "font/woff2") == "unknown_to_the_rules"
    assert S.verdict("png", "image/jpeg") == "disagree" and S.verdict("text", "application/octet-stream") == "disagree"


def test_note_categories_hide_entry_names():
    for note, label in (("the name says png but the contents are text", "name_disagrees"), ("entry name leaves its folder: ../x", "entry_leaves_folder"),
                        ("has encrypted entries", "encrypted_entries"), ("unpacks to a program or script", "unpacks_to_program"),
                        ("2 entries are programs or scripts", "program_entries"), ("1 nested archive", "nested_archives"),
                        ("unpacks to 20 MiB", "unpacks_to_huge"), ("high entropy (7.9 of 8)", "high_entropy"), ("entry does not read: a", "entry_unreadable"),
                        ("13 bytes follow the end of the image", "after_image"), ("3 bytes follow the end of the stream", "after_stream"),
                        ("xz stream does not decode (LZMAError)", "broken"), ("gzip stream is cut short", "broken"), ("anything else", "other")):
        assert S.note_category(note) == label, note


def test_summary():
    rows = [{"kind": "png", "mime": "image/png", "verdict": "agree", "notes": []},
            {"kind": "unknown_binary", "mime": "application/octet-stream", "verdict": "both_generic", "notes": ["high_entropy"]},
            {"kind": "unknown_binary", "mime": "font/woff2", "verdict": "unknown_to_the_rules", "notes": []},
            {"kind": "unknown_binary", "mime": "font/woff2", "verdict": "unknown_to_the_rules", "notes": []},
            {"kind": "zip", "mime": "text/plain", "verdict": "disagree", "notes": ["name_disagrees", "high_entropy"]},
            {"kind": "zip", "mime": "text/plain", "verdict": "disagree", "notes": []}, {"kind": "zip", "mime": "text/plain", "verdict": "disagree", "notes": []}]
    s = S.summarize(rows, 7)
    assert s["pull_requests_examined"] == 7 and s["files_read"] == 7
    assert s["by_verdict"]["agree"] == 1 and s["by_verdict"]["both_generic"] == 1 and s["by_verdict"]["unknown_to_the_rules"] == 2
    assert s["by_verdict"]["disagree"] == 3 and s["share_agree_or_both_generic"] == round(2 / 7, 4) and s["files_with_a_note"] == 2
    assert s["by_kind"] == {"png": 1, "unknown_binary": 3, "zip": 3} and s["notes_by_category"] == {"high_entropy": 2, "name_disagrees": 1}
    assert s["differences"][0] == {"rules": "zip", "file": "text/plain", "files": 3}            # most files first
    assert s["differences"][1] == {"rules": "unknown_binary", "file": "font/woff2", "files": 2} and len(s["differences"]) == 2
    assert S.summarize([], 3)["share_agree_or_both_generic"] is None


@pytest.mark.skipif(shutil.which("file") is None, reason="file(1) is not installed")
def test_file_mime_runs_file_on_standard_input():
    import base64
    png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")
    assert S.file_mime(png) == "image/png" and U.kind_of(png) == "png"
    assert S.file_mime(b"just some words\n") == "text/plain"


@pytest.mark.skipif(shutil.which("file") is None, reason="file(1) is not installed")
def test_the_rules_and_file_agree_on_small_blobs_made_here():
    """Compressed streams, a script and plain text: file(1) names these the same on every version. A tiny zip is left out:
    file(1) 5.44 (the CI image) calls a one-entry zip application/octet-stream where 5.45 says application/zip."""
    import bz2, gzip, lzma
    for data in (gzip.compress(b"abc"), bz2.compress(b"abc"), lzma.compress(b"abc"), b"#!/bin/sh\necho hi\n", b"plain\n"):
        kind = U.kind_of(data)
        assert S.verdict(kind, S.file_mime(data)) == "agree", (kind, S.file_mime(data))
