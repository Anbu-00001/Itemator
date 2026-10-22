import json
import urllib.error
import urllib.request


class FetchError(Exception):
    pass


def fetch_json(url: str, timeout: float = 10.0, opener=urllib.request.urlopen):
    """GET url and parse the body as JSON. `opener` is replaceable for tests."""
    req = urllib.request.Request(url, headers={"User-Agent": "fetchit/0.2"})
    try:
        with opener(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        raise FetchError(f"could not fetch {url}: {e}") from e
