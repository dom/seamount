"""describe-forge GET /pubkey endpoint shape."""
from __future__ import annotations


def test_pubkey_endpoint_shape(initialized_forge):
    """200 + {identity: 'describe-forge-local', key_scheme: 'brine', pubkey: <64-char hex>}."""
    service, identity, app = initialized_forge
    tc = app.test_client()
    r = tc.get("/pubkey")
    assert r.status_code == 200
    body = r.get_json()
    assert body["identity"] == identity
    assert body["key_scheme"] == "brine"
    assert isinstance(body["pubkey"], str)
    assert len(body["pubkey"]) == 64
    int(body["pubkey"], 16)
