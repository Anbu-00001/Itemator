"""What is inside a file nobody can read in a review? Standard library only; no model, no network, nothing is run.

`look(data, path)` names the kind of a blob from its first bytes (not from its name), says in one plain line what the
rules found inside, and lists notes a reviewer would want to know: a name that disagrees with the contents, an archive
or compressed stream that does not decode, bytes after the end of a PNG image, an archive entry whose name leaves its
folder, a stream that unpacks to a program. Decompression is capped (MAX_OUT bytes) so a small file cannot fill memory.

It reports facts and never says a file is safe or malicious. A reviewer reads the line; the rules do not judge."""
from __future__ import annotations

import bz2
import gzip
import io
import lzma
import math
import tarfile
import zipfile
import zlib
from dataclasses import dataclass

MAX_OUT = 16 * 1024 * 1024
ENTROPY_SAMPLE = 65536
HIGH_ENTROPY = 7.5

_ELF_MACHINE = {0x03: "x86", 0x08: "MIPS", 0x14: "PowerPC", 0x28: "ARM", 0x3E: "x86-64", 0xB7: "AArch64", 0xF3: "RISC-V"}
_PROGRAMS = ("elf", "pe", "macho", "wasm", "java_class", "script")
_EXT_KIND = {"png": "png", "jpg": "jpeg", "jpeg": "jpeg", "gif": "gif", "zip": "zip", "jar": "zip", "whl": "zip", "apk": "zip",
             "gz": "gzip", "tgz": "gzip", "bz2": "bzip2", "xz": "xz", "lzma": "lzma", "tar": "tar", "pdf": "pdf",
             "wasm": "wasm", "class": "java_class", "so": "elf", "exe": "pe", "dll": "pe", "sh": "script", "txt": "text",
             "json": "text", "md": "text", "py": "text", "js": "text", "csv": "text", "xml": "text", "yml": "text", "yaml": "text"}
_ARCHIVES = ("zip", "gzip", "bzip2", "xz", "lzma", "tar")
_ZIP_EXEC_EXT = (".so", ".dll", ".exe", ".dylib", ".class", ".sh", ".bat", ".ps1", ".wasm")


@dataclass(frozen=True)
class Look:
    kind: str
    summary: str
    notes: tuple[str, ...] = ()

    def line(self) -> str:
        return self.summary + ("; " + "; ".join(self.notes) if self.notes else "")


def kind_of(data: bytes) -> str:
    """The kind from the first bytes alone."""
    h = data[:16]
    if not data:
        return "empty"
    if h[:4] == b"\x7fELF":
        return "elf"
    if h[:2] == b"MZ" and len(data) > 0x40:
        pe = int.from_bytes(data[0x3C:0x40], "little")
        if data[pe:pe + 4] == b"PE\0\0":
            return "pe"
    if h[:4] in (b"\xfe\xed\xfa\xce", b"\xce\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe"):
        return "java_class" if h[:4] == b"\xca\xfe\xba\xbe" and int.from_bytes(h[6:8], "big") >= 44 else "macho"
    if h[:4] == b"\0asm":
        return "wasm"
    if h[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if h[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if h[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if h[:4] in (b"PK\x03\x04", b"PK\x05\x06"):
        return "zip"
    if h[:2] == b"\x1f\x8b":
        return "gzip"
    if h[:3] == b"BZh":
        return "bzip2"
    if h[:6] == b"\xfd7zXZ\0":
        return "xz"
    if h[:3] == b"\x5d\0\0" and len(data) > 13:
        return "lzma"
    if h[:5] == b"%PDF-":
        return "pdf"
    if len(data) > 262 and data[257:262] == b"ustar":
        return "tar"
    if h[:2] == b"#!":
        return "script"
    if _is_text(data):
        return "text"
    return "unknown_binary"


def _is_text(data: bytes) -> bool:
    sample = data[:8192]
    if b"\0" in sample:
        return False
    try:
        sample.decode("utf-8")
    except UnicodeDecodeError as e:
        if e.start < len(sample) - 3:           # a character cut at the end of the sample is not an error
            return False
    return True


def entropy(data: bytes) -> float:
    sample = data[:ENTROPY_SAMPLE]
    counts = [0] * 256
    for b in sample:
        counts[b] += 1
    n = len(sample)
    return -sum(c / n * math.log2(c / n) for c in counts if c)


def _ext(path: str) -> str:
    name = path.rsplit("/", 1)[-1]
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def _size(n: int) -> str:
    return f"{n} bytes" if n < 10240 else f"{n / 1024:.0f} KiB" if n < 10 * 1024 * 1024 else f"{n / 1048576:.0f} MiB"


def _unpack(kind: str, data: bytes) -> tuple[bytes | None, str, int]:
    """(output, problem, bytes left over after the stream). Output is capped at MAX_OUT."""
    try:
        if kind == "gzip":
            d = zlib.decompressobj(31)
            out = d.decompress(data, MAX_OUT)
            return out, "" if d.eof or len(out) >= MAX_OUT else "gzip stream is cut short", len(d.unused_data)
        if kind == "bzip2":
            d = bz2.BZ2Decompressor()
            out = d.decompress(data, MAX_OUT)
            return out, "" if d.eof or len(out) >= MAX_OUT else "bzip2 stream is cut short", len(d.unused_data)
        d = lzma.LZMADecompressor(format=lzma.FORMAT_AUTO)
        out = d.decompress(data, MAX_OUT)
        return out, "" if d.eof or len(out) >= MAX_OUT else f"{kind} stream is cut short", len(d.unused_data)
    except (zlib.error, OSError, EOFError, lzma.LZMAError, ValueError) as e:
        return None, f"{kind} stream does not decode ({type(e).__name__})", 0


def _inner(data: bytes) -> str:
    k = kind_of(data)
    return {"unknown_binary": "binary data", "java_class": "a Java class", "elf": "a Linux program", "pe": "a Windows program",
            "macho": "a macOS program", "wasm": "a WebAssembly module", "script": "a script", "text": "text"}.get(k, k)


def _zip(data: bytes) -> tuple[str, list[str]]:
    notes: list[str] = []
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
        infos = zf.infolist()
    except (zipfile.BadZipFile, ValueError, OSError):
        return "zip archive that does not open", ["the end-of-archive record is damaged or missing"]
    names = [i.filename for i in infos]
    bad = [n for n in names if n.startswith("/") or ".." in n.replace("\\", "/").split("/")]
    if bad:
        notes.append(f"entry name leaves its folder: {bad[0]}")
    if any(i.flag_bits & 1 for i in infos):
        notes.append("has encrypted entries")
    programs = 0
    nested = 0
    for i in infos[:2000]:
        if i.is_dir() or i.flag_bits & 1:
            continue
        try:
            with zf.open(i) as f:
                head = f.read(16)
        except (zipfile.BadZipFile, NotImplementedError, RuntimeError, zlib.error, OSError, EOFError, lzma.LZMAError, ValueError):
            notes.append(f"entry does not read: {i.filename}")
            continue
        k = kind_of(head)
        if k in _PROGRAMS or i.filename.lower().endswith(_ZIP_EXEC_EXT):
            programs += 1
        if k in _ARCHIVES:
            nested += 1
    if programs:
        notes.append(f"{programs} entr{'y is a program or script' if programs == 1 else 'ies are programs or scripts'}")
    if nested:
        notes.append(f"{nested} nested archive{'s' if nested != 1 else ''}")
    total = sum(i.file_size for i in infos)
    if total > 64 * len(data) and total > MAX_OUT:
        notes.append(f"unpacks to {_size(total)}")
    return f"zip archive of {len(infos)} entr{'y' if len(infos) == 1 else 'ies'}", notes


def _after_png(data: bytes) -> int:
    """Bytes after the IEND chunk of a PNG, found by walking the length-prefixed chunks; 0 when the walk does not end at IEND."""
    pos = 8
    while pos + 12 <= len(data):
        n = int.from_bytes(data[pos:pos + 4], "big")
        kind = data[pos + 4:pos + 8]
        pos += 12 + n
        if kind == b"IEND":
            return max(0, len(data) - pos)
    return 0


def _mismatch(claimed: str, kind: str) -> bool:
    """A name that promises one format while the first bytes show another. A text name over a script is not a mismatch."""
    if claimed == kind:
        return False
    if claimed == "text":
        return kind in _PROGRAMS[:-1] or kind in _ARCHIVES or kind in ("png", "jpeg", "gif", "pdf", "unknown_binary")
    if claimed == "script":
        return kind != "text"
    return True


def look(data: bytes, path: str = "") -> Look:
    kind = kind_of(data)
    notes: list[str] = []
    claimed = _EXT_KIND.get(_ext(path))
    if claimed and kind != "empty" and _mismatch(claimed, kind):
        notes.append(f"the name says {_ext(path)} but the contents are {_inner(data) if kind in _PROGRAMS or kind in ('unknown_binary', 'text') else kind}")
    size = _size(len(data))
    if kind == "empty":
        return Look(kind, "empty file")
    if kind in ("elf", "pe", "macho", "wasm", "java_class"):
        what = {"elf": "Linux program or library", "pe": "Windows program or library", "macho": "macOS program or library",
                "wasm": "WebAssembly module", "java_class": "Java class file"}[kind]
        if kind == "elf" and len(data) > 19:
            arch = _ELF_MACHINE.get(int.from_bytes(data[18:20], "little" if data[5] == 1 else "big"))
            if arch:
                what += f" for {arch}"
        return Look(kind, f"{what}, {size}", tuple(notes))
    if kind in ("png", "jpeg", "gif"):
        extra = _after_png(data) if kind == "png" else 0
        if extra:
            notes.append(f"{_size(extra)} follow the end of the image")
        return Look(kind, f"{kind.upper()} image, {size}", tuple(notes))
    if kind == "zip":
        summary, more = _zip(data)
        return Look(kind, f"{summary}, {size}", tuple(notes + more))
    if kind in ("gzip", "bzip2", "xz", "lzma"):
        out, problem, left = _unpack(kind, data)
        if problem:
            e = entropy(data)
            return Look(kind, f"{kind} file, {size}", tuple(notes + [problem] + ([f"high entropy ({e:.1f} of 8)"] if e >= HIGH_ENTROPY else [])))
        capped = len(out) >= MAX_OUT
        inner = _inner(out)
        k2 = kind_of(out)
        if k2 == "tar":
            try:
                with tarfile.open(fileobj=io.BytesIO(out)) as tf:
                    members = tf.getmembers()
                inner = f"a tar archive of {len(members)} entr{'y' if len(members) == 1 else 'ies'}"
                bad = [m.name for m in members if m.name.startswith("/") or ".." in m.name.split("/")]
                if bad:
                    notes.append(f"entry name leaves its folder: {bad[0]}")
            except (tarfile.TarError, EOFError, OSError):
                inner = "a damaged tar archive"
        if left:
            notes.append(f"{_size(left)} follow the end of the stream")
        if k2 in _PROGRAMS:
            notes.append("unpacks to a program or script")
        return Look(kind, f"{kind} file, {size}, unpacks to {'at least ' if capped else ''}{_size(len(out))} of {inner}", tuple(notes))
    if kind == "tar":
        try:
            with tarfile.open(fileobj=io.BytesIO(data)) as tf:
                members = tf.getmembers()
            bad = [m.name for m in members if m.name.startswith("/") or ".." in m.name.split("/")]
            if bad:
                notes.append(f"entry name leaves its folder: {bad[0]}")
            return Look(kind, f"tar archive of {len(members)} entr{'y' if len(members) == 1 else 'ies'}, {size}", tuple(notes))
        except (tarfile.TarError, EOFError, OSError):
            return Look(kind, f"tar archive that does not open, {size}", tuple(notes))
    if kind == "unknown_binary":
        e = entropy(data)
        if e >= HIGH_ENTROPY:
            notes.append(f"high entropy ({e:.1f} of 8): compressed or encrypted data in no format the rules know")
        return Look(kind, f"binary data in no format the rules know, {size}", tuple(notes))
    return Look(kind, f"{kind}, {size}", tuple(notes))
