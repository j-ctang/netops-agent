import httpx
import pytest

from netops_agent.client import MerakiClient, MerakiError


def make(handler, **kw):
    return MerakiClient(api_key="k", transport=httpx.MockTransport(handler), sleep=lambda s: None, **kw)


def test_sends_bearer_key_and_base_url():
    seen = {}

    def handler(req):
        seen["auth"] = req.headers["authorization"]
        seen["url"] = str(req.url)
        return httpx.Response(200, json=[])

    make(handler).get("/organizations")
    assert seen == {"auth": "Bearer k", "url": "https://api.meraki.com/api/v1/organizations"}


def test_retries_429_using_retry_after():
    waits, codes = [], iter([429, 429, 200])

    def handler(req):
        code = next(codes)
        return httpx.Response(code, headers={"Retry-After": "3"}, json=[{"id": "1"}] if code == 200 else {})

    c = MerakiClient(api_key="k", transport=httpx.MockTransport(handler), sleep=waits.append)
    assert c.get("/organizations") == [{"id": "1"}]
    assert waits == [3.0, 3.0]
    assert c.calls == 3


def test_gives_up_after_max_retries():
    c = make(lambda req: httpx.Response(429, json={}), max_retries=2)
    with pytest.raises(MerakiError, match="rate limited"):
        c.get("/organizations")
    assert c.calls == 3


def test_follows_link_next_pages():
    def handler(req):
        if req.url.params.get("startingAfter") == "a":
            return httpx.Response(200, json=[{"id": "b"}])
        nxt = "https://api.meraki.com/api/v1/organizations?startingAfter=a"
        return httpx.Response(200, json=[{"id": "a"}], headers={"Link": f"<{nxt}>; rel=next"})

    c = make(handler)
    assert c.get("/organizations") == [{"id": "a"}, {"id": "b"}]
    assert c.calls == 2


def test_http_error_raises():
    with pytest.raises(MerakiError, match="401"):
        make(lambda req: httpx.Response(401, json={"errors": ["bad key"]})).get("/organizations")
