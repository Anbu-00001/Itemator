import configparser

DEFAULTS = {"timeout": "10"}


def load(path: str) -> dict:
    """Settings from an INI file's [fetchit] section, over DEFAULTS."""
    cp = configparser.ConfigParser()
    cp.read(path)
    out = dict(DEFAULTS)
    if cp.has_section("fetchit"):
        out.update(cp["fetchit"])
    return out
