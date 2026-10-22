import io

from fetchit import fetch_json


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_fetch_json_parses_body():
    assert fetch_json("http://x.invalid/", opener=lambda req, timeout: Resp(b'{"a": 1}')) == {"a": 1}
