from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register(client: AsyncClient):
    resp = await client.post("/api/auth/register", json={
        "email": "new@example.com",
        "password": "strongpassword",
        "display_name": "New User",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert "access_token" in data


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient):
    await client.post("/api/auth/register", json={
        "email": "dup@example.com",
        "password": "pass123",
    })
    resp = await client.post("/api/auth/register", json={
        "email": "dup@example.com",
        "password": "pass456",
    })
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_login(client: AsyncClient):
    await client.post("/api/auth/register", json={
        "email": "login@example.com",
        "password": "mypassword",
    })
    resp = await client.post("/api/auth/login", json={
        "email": "login@example.com",
        "password": "mypassword",
    })
    assert resp.status_code == 200
    assert "access_token" in resp.json()


@pytest.mark.asyncio
async def test_login_bad_password(client: AsyncClient):
    await client.post("/api/auth/register", json={
        "email": "badpw@example.com",
        "password": "correctpassword",
    })
    resp = await client.post("/api/auth/login", json={
        "email": "badpw@example.com",
        "password": "wrongpassword",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_logout(client: AsyncClient):
    resp = await client.post("/api/auth/logout")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_me(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "test@example.com"


@pytest.mark.asyncio
async def test_me_unauthorized(client: AsyncClient):
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_invalid_token(client: AsyncClient):
    resp = await client.get("/api/auth/me", headers={"Authorization": "Bearer invalid.token.here"})
    assert resp.status_code == 401
