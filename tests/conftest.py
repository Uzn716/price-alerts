import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class FakeResponse:
    def __init__(self, status=200, body=None, content=None):
        self.status_code = status
        self._body = body
        self.content = content if content is not None else json.dumps(body or {}).encode()
        self.text = self.content.decode("utf-8", "replace")

    def json(self):
        if self._body is None:
            return json.loads(self.content)
        return self._body


class FakeSession:
    """Routes requests by URL substring; records everything sent."""

    def __init__(self, routes, post_routes=None):
        self.routes = routes  # list of (substring, FakeResponse or callable)
        self.post_routes = post_routes or []
        self.calls = []
        self.posts = []
        self.headers = {}

    def get(self, url, params=None, timeout=None, headers=None):
        self.calls.append((url, params or {}))
        for needle, resp in self.routes:
            if needle in url:
                return resp(url, params) if callable(resp) else resp
        raise AssertionError(f"unexpected GET {url}")

    def post(self, url, json=None, params=None, timeout=None, data=None, headers=None):
        for needle, resp in self.post_routes:
            if needle in url:
                self.calls.append((url, data or {}))
                return resp(url, data) if callable(resp) else resp
        self.posts.append(json)
        return FakeResponse(200, {"id": "1"})


@pytest.fixture
def root():
    return ROOT
