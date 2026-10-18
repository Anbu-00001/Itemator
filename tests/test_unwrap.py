"""itemator/unwrap.py: what the rules say is inside a file nobody can read, built from small blobs made in the tests."""
import bz2
import gzip
import io
import lzma
import tarfile
import zipfile

from itemator import unwrap as U
from itemator.unwrap import look

ELF = b"\x7fELF\x02\x01\x01" + b"\0" * 9 + b"\x02\0\x3e\0" + b"\0" * 100
PNG_HEAD = b"\x89PNG\r\n\x1a\n" + b"\0\0\0\rIHDR" + b"\0" * 13 + b"\0\0\0\0"
PNG_END = b"\0\0\0\0IEND\xaeB`\x82"


def zipped(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in entries:
            z.writestr(name, data)
    return buf.getvalue()


def tarred(names):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as t:
        for n in names:
            info = tarfile.TarInfo(n)
            info.size = 2
            t.addfile(info, io.BytesIO(b"hi"))
    return buf.getvalue()


def test_kinds_come_from_the_first_bytes_not_the_name():
    assert U.kind_of(ELF) == "elf" and U.kind_of(b"\0asm\x01\0\0\0") == "wasm" and U.kind_of(b"") == "empty"
    assert U.kind_of(PNG_HEAD + PNG_END) == "png" and U.kind_of(b"\xff\xd8\xff\xe0abc") == "jpeg" and U.kind_of(b"GIF89a....") == "gif"
    assert U.kind_of(zipped([("a", b"x")])) == "zip" and U.kind_of(gzip.compress(b"a")) == "gzip" and U.kind_of(bz2.compress(b"a")) == "bzip2"
    assert U.kind_of(lzma.compress(b"a")) == "xz" and U.kind_of(lzma.compress(b"a", format=lzma.FORMAT_ALONE)) == "lzma"
    assert U.kind_of(b"%PDF-1.7\n") == "pdf" and U.kind_of(tarred(["a"])) == "tar"
    assert U.kind_of(b"#!/bin/sh\n") == "script" and U.kind_of(b"just text\n") == "text" and U.kind_of(b"a\0b") == "unknown_binary"
    assert U.kind_of(b"\xca\xfe\xba\xbe\0\0\0\x34") == "java_class" and U.kind_of(b"\xca\xfe\xba\xbe\0\0\0\x02") == "macho"
    pe = bytearray(0x80)
    pe[:2], pe[0x3C:0x40], pe[0x40:0x44] = b"MZ", (0x40).to_bytes(4, "little"), b"PE\0\0"
    assert U.kind_of(bytes(pe)) == "pe" and U.kind_of(b"MZ" + b"\0" * 200) == "unknown_binary"


def test_text_cut_in_the_middle_of_a_character_is_still_text():
    assert U.kind_of(("é" * 5000).encode()[:8191]) == "text"
    assert U.kind_of(b"abc\xff\xfe" + b"x" * 100) == "unknown_binary"


def test_a_program_names_its_architecture_and_size():
    v = look(ELF, "lib/x.so")
    assert v.kind == "elf" and v.summary == "Linux program or library for x86-64, 120 bytes" and v.notes == ()
    assert look(ELF[:18] + b"\xb7\0" + ELF[20:], "x").summary.startswith("Linux program or library for AArch64")


def test_a_name_that_disagrees_with_the_contents_is_noted():
    assert look(ELF, "logo.png").notes == ("the name says png but the contents are a Linux program",)
    assert look(b"hello\n", "logo.png").notes == ("the name says png but the contents are text",)
    assert look(PNG_HEAD + PNG_END, "logo.png").notes == ()
    assert look(zipped([("a", b"x")]), "lib.jar").notes == () and look(b"\0\1\2", "a.dat").notes == ()
    assert look(b"#!/bin/sh\n", "a.txt").notes == () and look(b"#!/bin/sh\n", "a.sh").notes == ()
    assert "the name says sh" in look(ELF, "run.sh").notes[0] and "the name says txt" in look(ELF, "n.txt").notes[0]
    assert look(b"plain", "a.sh").notes == ()                                               # text under a script name is fine


def test_bytes_after_the_end_of_a_png_are_counted():
    assert look(PNG_HEAD + PNG_END + b"PAYLOAD!!", "a.png").notes == ("9 bytes follow the end of the image",)
    assert look(PNG_HEAD + PNG_END, "a.png").notes == ()
    assert look(PNG_HEAD, "a.png").notes == ()                                              # no IEND: nothing is claimed


def test_a_zip_lists_entries_programs_and_names_that_leave_the_folder():
    v = look(zipped([("a.txt", b"hi"), ("lib/x.bin", ELF), ("run.sh", b"#!/bin/sh\n"), ("../up.txt", b"x")]), "pkg.whl")
    assert v.summary == "zip archive of 4 entries, " + v.summary.split(", ")[1]
    assert "entry name leaves its folder: ../up.txt" in v.notes and "2 entries are programs or scripts" in v.notes
    assert look(zipped([("a.txt", b"hi")]), "x.zip").summary.startswith("zip archive of 1 entry,")
    assert look(zipped([("/abs.txt", b"x")]), "x.zip").notes == ("entry name leaves its folder: /abs.txt",)
    assert look(zipped([("a/b.so", b"not really")]), "x.zip").notes == ("1 entry is a program or script",)     # by name
    assert "1 nested archive" in look(zipped([("in.zip", zipped([("a", b"x")]))]), "x.zip").notes


def test_a_zip_with_a_damaged_end_does_not_open():
    v = look(zipped([("a.txt", b"hi")])[:-10], "x.zip")
    assert v.kind == "zip" and v.summary.startswith("zip archive that does not open, ") and v.notes


def test_encrypted_zip_entries_are_noted():
    data = bytearray(zipped([("a.txt", b"hello")]))
    i = data.find(b"PK\x01\x02")
    data[i + 8] |= 1                                    # general purpose flag bit 0 in the central directory
    j = data.find(b"PK\x03\x04")
    data[j + 6] |= 1
    assert "has encrypted entries" in look(bytes(data), "x.zip").notes


def test_a_compressed_stream_says_what_it_unpacks_to():
    assert look(gzip.compress(b"#!/bin/sh\necho hi\n"), "d.gz").summary.endswith("unpacks to 18 bytes of a script")
    assert look(gzip.compress(b"#!/bin/sh\necho hi\n"), "d.gz").notes == ("unpacks to a program or script",)
    assert look(bz2.compress(b"hello" * 100), "d.bz2").summary.endswith("unpacks to 500 bytes of text")
    assert look(lzma.compress(ELF), "d.xz").notes == ("unpacks to a program or script",)
    assert look(lzma.compress(ELF, format=lzma.FORMAT_ALONE), "d.lzma").summary.endswith("of a Linux program")
    assert look(gzip.compress(bytes(range(256)) * 4), "d.gz").summary.endswith("of binary data")


def test_a_stream_that_is_cut_short_or_corrupt_is_said_so():
    good = lzma.compress(b"hello" * 200)
    assert look(good[:-20], "t.xz").notes == ("xz stream is cut short",)
    bad = bytearray(good)
    bad[40] ^= 0xFF
    n = look(bytes(bad), "t.xz").notes
    assert n and n[0].startswith("xz stream does not decode (LZMAError") or n[0] == "xz stream is cut short"
    assert look(gzip.compress(b"abc" * 100)[:-8], "t.gz").notes == ("gzip stream is cut short",)
    assert look(bz2.compress(b"abc" * 100)[:-10], "t.bz2").notes == ("bzip2 stream is cut short",)
    assert look(b"\x1f\x8b" + b"\xff" * 40, "t.gz").notes[0].startswith("gzip stream does not decode")
    assert look(b"BZh9" + b"\xff" * 40, "t.bz2").notes[0].startswith("bzip2 stream does not decode")


def test_a_stream_that_does_not_decode_and_looks_random_says_so():
    import random
    r = random.Random(1)
    blob = b"\xfd7zXZ\0" + bytes(r.randrange(256) for _ in range(4000))
    v = look(blob, "t.xz")
    assert v.notes[0].startswith("xz stream does not decode") and any(n.startswith("high entropy") for n in v.notes)
    low = look(b"\xfd7zXZ\0" + b"\0" * 400, "t.xz")
    assert not any(n.startswith("high entropy") for n in low.notes)


def test_bytes_after_the_end_of_a_stream_are_counted():
    assert look(gzip.compress(b"abc" * 50) + b"TRAILING-DATA", "t.gz").notes == ("13 bytes follow the end of the stream",)
    assert look(gzip.compress(b"abc" * 50), "t.gz").notes == ()


def test_unpacking_is_capped():
    big = gzip.compress(b"\0" * (U.MAX_OUT + 4096))
    v = look(big, "bomb.gz")
    assert "unpacks to at least 16 MiB" in v.summary
    assert look(gzip.compress(b"\0" * 1000), "ok.gz").summary.find("at least") == -1


def test_a_tar_inside_a_stream_or_alone_lists_entries_and_bad_names():
    assert look(tarred(["a", "b"]), "x.tar").summary.startswith("tar archive of 2 entries,")
    assert look(tarred(["../evil"]), "x.tar").notes == ("entry name leaves its folder: ../evil",)
    inner = look(gzip.compress(tarred(["a"])), "x.tgz")
    assert inner.summary.endswith("of a tar archive of 1 entry") and inner.notes == ()
    assert look(gzip.compress(tarred(["/etc/x"])), "x.tgz").notes == ("entry name leaves its folder: /etc/x",)
    damaged = bytearray(tarred(["a"]))
    damaged[148:156] = b"zzzzzzzz"                                                        # checksum field
    assert look(bytes(damaged), "x.tar").summary.startswith("tar archive that does not open")


def test_high_entropy_unknown_data_is_flagged_and_ordinary_data_is_not():
    import random
    r = random.Random(2)
    rnd = bytes(r.randrange(256) for _ in range(5000))
    assert any(n.startswith("high entropy") for n in look(rnd, "blob.bin").notes)
    assert look(b"\0\1\2\3" * 1000, "blob.bin").notes == ()
    assert U.entropy(b"") == 0.0 and abs(U.entropy(bytes(range(256)) * 4) - 8.0) < 1e-9 and U.entropy(b"aaaa") == 0.0


def test_empty_and_unknown_and_plain_files():
    assert look(b"", "x.bin").summary == "empty file"
    assert look(b"\0\1\2", "x.bin").summary == "binary data in no format the rules know, 3 bytes"
    assert look(b"hello\n", "notes.txt").line() == "text, 6 bytes"


def test_line_joins_summary_and_notes():
    v = look(PNG_HEAD + PNG_END + b"XY", "a.png")
    assert v.line() == "PNG image, 47 bytes; 2 bytes follow the end of the image"


def test_sizes_read_in_plain_units():
    assert U._size(10239) == "10239 bytes" and U._size(10240) == "10 KiB" and U._size(10 * 1024 * 1024) == "10 MiB"


def test_an_empty_zip_and_a_short_lzma_header():
    assert U.kind_of(b"PK\x05\x06" + b"\0" * 18) == "zip"
    assert U.kind_of(b"\x5d\0\0\1") == "unknown_binary"          # too short to be an lzma file


def test_every_decompressor_stops_at_the_cap():
    zeros = b"\0" * (U.MAX_OUT + 4096)
    for kind, packed in (("gzip", gzip.compress(zeros)), ("bzip2", bz2.compress(zeros)), ("xz", lzma.compress(zeros)),
                         ("lzma", lzma.compress(zeros, format=lzma.FORMAT_ALONE))):
        out, problem, left = U._unpack(kind, packed)
        assert len(out) == U.MAX_OUT and problem == "" and left == 0, kind


def test_a_small_zip_that_unpacks_to_a_huge_size_is_noted():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("zeros.bin", b"\0" * (20 * 1024 * 1024))
    v = look(buf.getvalue(), "bomb.zip")
    assert "unpacks to 20 MiB" in v.notes
    assert not any(n.startswith("unpacks") for n in look(zipped([("a", b"\0" * 5000)]), "x.zip").notes)


def test_a_short_elf_header_still_names_the_machine():
    assert look(ELF[:40], "x").summary == "Linux program or library for x86-64, 40 bytes"
    head = b"\x7fELF\x02\x02\x01" + b"\0" * 9 + b"\0\x02"                          # big-endian, an executable
    assert look(head + b"\0\x15", "x").summary == "Linux program or library, 20 bytes"      # a machine the table does not hold
    assert look(head + b"\0\x28", "x").summary == "Linux program or library for ARM, 20 bytes"
    assert look(head + b"\x28\0", "x").summary == "Linux program or library, 20 bytes"      # read as big-endian, 0x2800 is not ARM
