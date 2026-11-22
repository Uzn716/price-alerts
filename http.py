"""HTTP session with sensible timeouts and retries."""
from __future__ import annotations

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

USER_AGENT = "pc-price-alerts/1.0 (personal price-error notifier; +https://github.com)"
TIMEOUT = 20


class SourceError(Exception):
    """A store/data source failed in a way worth reporting."""


def make_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=2,
        backoff_factor=1.5,
        status_forcelist=(500, 502, 503, 504),
        allowed_methods=("GET",),
        raise_on_status=False,
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers["User-Agent"] = USER_AGENT
    return session
