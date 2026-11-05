# ruff: noqa: B008 -- FastAPI evaluates dependency declarations at registration.
"""Authenticated, single-organization pilot API. Run behind a TLS reverse proxy."""

import asyncio
import json
import os
import sqlite3
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import jwt
from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from .operations import COUNTS
from .runtime import close_runtime
from .server import gene_evidence


class Export(BaseModel):
    report: str = Field(min_length=1, max_length=262144)


def create_app():
    issuer, audience, jwks, grants, db = (
        os.environ[k]
        for k in (
            "BIOMCP_ISSUER",
            "BIOMCP_AUDIENCE",
            "BIOMCP_JWKS_URL",
            "BIOMCP_GRANTS",
            "BIOMCP_EXPORT_DB",
        )
    )
    if not issuer.startswith("https://") or not jwks.startswith("https://") or not audience:
        raise ValueError("Configure an HTTPS issuer, trusted JWKS endpoint and audience.")
    if not os.environ.get("BIOMCP_REDIS_URL"):
        raise ValueError("Shared Redis coordination is required.")
    keys = jwt.PyJWKClient(jwks, timeout=3)

    def database():
        return sqlite3.connect(db, timeout=3)

    def sweep():
        with database() as conn:
            conn.execute("DELETE FROM exports WHERE expires <= ?", (time.time(),))

    @asynccontextmanager
    async def lifespan(app):
        with database() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS exports (id TEXT PRIMARY KEY, owner TEXT, expires REAL, body TEXT)"
            )

        async def cleaner():
            while True:
                await asyncio.to_thread(sweep)
                await asyncio.sleep(60)

        task = asyncio.create_task(cleaner())
        try:
            yield
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            await close_runtime()

    app = FastAPI(lifespan=lifespan)
    bearer = HTTPBearer(auto_error=False)

    def require(scope):
        def authorize(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
            if not credentials:
                raise HTTPException(401, "Bearer token required")
            try:
                token = credentials.credentials
                key = keys.get_signing_key_from_jwt(token).key
                claims = jwt.decode(
                    token,
                    key,
                    algorithms=["RS256"],
                    issuer=issuer,
                    audience=audience,
                    options={"require": ["exp", "sub", "iss", "aud"]},
                )
            except (jwt.PyJWTError, ValueError) as exc:
                raise HTTPException(401, "Invalid access token") from exc
            try:
                allowed = json.loads(Path(grants).read_text()).get(claims["sub"], [])
            except (OSError, ValueError, AttributeError) as exc:
                raise HTTPException(503, "Authorization policy unavailable") from exc
            if (
                not isinstance(allowed, list)
                or scope not in allowed
                or scope not in claims.get("scope", "").split()
            ):
                raise HTTPException(403, "Access denied")
            return claims["sub"]

        return authorize

    @app.get("/evidence/{query}")
    async def evidence(query: str, subject=Depends(require("research:public"))):
        try:
            return await gene_evidence(query)
        except ValueError as exc:
            raise HTTPException(422, "Identifier did not resolve uniquely") from exc

    @app.get("/operations")
    def operations(subject=Depends(require("operations:read"))):
        return dict(COUNTS)

    @app.post("/exports", status_code=201)
    def export(body: Export, subject=Depends(require("export:write"))):
        identifier = uuid.uuid4().hex
        expiry = time.time() + 3600
        with database() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("DELETE FROM exports WHERE expires <= ?", (time.time(),))
            if (
                conn.execute("SELECT count(*) FROM exports WHERE owner=?", (subject,)).fetchone()[0]
                >= 20
            ):
                raise HTTPException(429, "Export quota reached")
            conn.execute(
                "INSERT INTO exports VALUES (?,?,?,?)", (identifier, subject, expiry, body.report)
            )
        return {"id": identifier, "expires": expiry}

    @app.get("/exports/{identifier}")
    def download(identifier: str, subject=Depends(require("export:read"))):
        with database() as conn:
            row = conn.execute(
                "SELECT body FROM exports WHERE id=? AND owner=? AND expires>?",
                (identifier, subject, time.time()),
            ).fetchone()
        if not row:
            raise HTTPException(404, "Export unavailable")
        return Response(
            row[0],
            media_type="text/plain",
            headers={
                "Cache-Control": "no-store",
                "Content-Disposition": 'attachment; filename="report.txt"',
            },
        )

    return app
