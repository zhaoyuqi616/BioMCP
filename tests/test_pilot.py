import json
import sqlite3
import time
from types import SimpleNamespace

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from ensembl_uniprot_mcp.pilot import create_app


def test_signed_access_export_isolation_expiration_and_revocation(tmp_path, monkeypatch):
    grants = tmp_path / "grants.json"
    db = tmp_path / "exports.db"
    scopes = ["export:write", "export:read"]
    grants.write_text(json.dumps({"alice": scopes, "bob": scopes}))
    for k, v in {
        "ISSUER": "https://id.example",
        "AUDIENCE": "pilot",
        "JWKS_URL": "https://id.example/keys",
        "GRANTS": str(grants),
        "EXPORT_DB": str(db),
        "REDIS_URL": "redis://localhost",
    }.items():
        monkeypatch.setenv("BIOMCP_" + k, v)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(
        jwt.PyJWKClient,
        "get_signing_key_from_jwt",
        lambda *args: SimpleNamespace(key=key.public_key()),
    )

    def headers(sub, aud="pilot"):
        token = jwt.encode(
            {
                "sub": sub,
                "exp": time.time() + 300,
                "iss": "https://id.example",
                "aud": aud,
                "scope": " ".join(scopes),
            },
            key,
            algorithm="RS256",
        )
        return {"Authorization": "Bearer " + token}

    with TestClient(create_app()) as client:
        assert client.get("/evidence/SPP1").status_code == 401
        assert client.get("/exports/x", headers=headers("alice", "other")).status_code == 401
        item = client.post("/exports", json={"report": "public report"}, headers=headers("alice"))
        assert item.status_code == 201
        path = "/exports/" + item.json()["id"]
        assert client.get(path, headers=headers("bob")).status_code == 404
        assert client.get(path, headers=headers("alice")).text == "public report"
        grants.write_text("{}")
        assert client.get(path, headers=headers("alice")).status_code == 403
        grants.write_text(json.dumps({"alice": scopes}))
        with sqlite3.connect(db) as conn:
            conn.execute("UPDATE exports SET expires=0")
        assert client.get(path, headers=headers("alice")).status_code == 404
