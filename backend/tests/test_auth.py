from datetime import timedelta
import pytest
from app.core.security import create_access_token


def test_registration_succeeds(unauthed_client):
    response = unauthed_client.post(
        "/api/v1/auth/register",
        json={
            "email": "freshuser@provision.local",
            "password": "strongpassword123",
            "display_name": "Fresh User",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "freshuser@provision.local"
    assert data["display_name"] == "Fresh User"
    assert data["is_active"] is True
    assert "id" in data
    # Password hash must never be returned
    assert "password" not in data
    assert "hashed_password" not in data


def test_duplicate_email_rejected(unauthed_client, auth_user):
    response = unauthed_client.post(
        "/api/v1/auth/register",
        json={
            "email": auth_user.email,
            "password": "someotherpassword",
        },
    )
    assert response.status_code == 400
    assert "already registered" in response.json()["detail"].lower()


def test_password_hash_never_returned_on_me(unauthed_client, auth_headers):
    response = unauthed_client.get("/api/v1/auth/me", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "password" not in data
    assert "hashed_password" not in data


def test_login_succeeds(unauthed_client, auth_user):
    response = unauthed_client.post(
        "/api/v1/auth/login",
        json={
            "email": auth_user.email,
            "password": "password123",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert len(data["access_token"]) > 20


def test_wrong_password_fails_generic_401(unauthed_client, auth_user):
    response = unauthed_client.post(
        "/api/v1/auth/login",
        json={
            "email": auth_user.email,
            "password": "wrongpassword999",
        },
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


def test_nonexistent_email_fails_generic_401(unauthed_client):
    response = unauthed_client.post(
        "/api/v1/auth/login",
        json={
            "email": "nobody@provision.local",
            "password": "somepassword",
        },
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


def test_auth_me_with_valid_token(unauthed_client, auth_user, auth_headers):
    response = unauthed_client.get("/api/v1/auth/me", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == auth_user.email
    assert data["id"] == auth_user.id


def test_auth_me_fails_without_token(unauthed_client):
    response = unauthed_client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_auth_me_fails_with_invalid_token(unauthed_client):
    response = unauthed_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer invalid.token.string"},
    )
    assert response.status_code == 401


def test_auth_me_fails_with_expired_token(unauthed_client, auth_user):
    expired_token = create_access_token(
        subject=auth_user.email,
        expires_delta=timedelta(seconds=-10),  # expired 10s ago
    )
    response = unauthed_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert response.status_code == 401


def test_protected_pantry_endpoint_fails_without_token(unauthed_client):
    response = unauthed_client.get("/api/v1/products/")
    assert response.status_code == 401


def test_protected_pantry_endpoint_succeeds_with_token(unauthed_client, auth_headers):
    response = unauthed_client.get("/api/v1/products/", headers=auth_headers)
    assert response.status_code == 200
