"""No test may reach a package registry: itemator.registry's one network call is replaced for every test, and a test
that reached it fails. Tests that check the real fetch put their own stand-in in its place."""
import pytest

from itemator import registry


@pytest.fixture(autouse=True)
def no_registry(monkeypatch):
    calls = []

    def refuse(req, timeout):
        calls.append(req.full_url)
        raise registry.LookupFailed("network")
    monkeypatch.setattr(registry, "_open", refuse)
    yield
    assert not calls, f"a test reached a registry: {calls}"
