"""Authentication tests for web admin panel."""

from __future__ import annotations

from fastapi.testclient import TestClient

import admin_panel.app as admin_app


def test_admin_panel_requires_basic_auth() -> None:
    """Request without credentials should be rejected."""
    client = TestClient(admin_app.app)
    response = client.get("/")
    assert response.status_code == 401


def test_admin_panel_allows_valid_credentials() -> None:
    """Request with valid credentials should pass."""
    admin_app.settings.admin_password = "test-secret"
    client = TestClient(admin_app.app)
    response = client.get("/", auth=("admin", "test-secret"))
    assert response.status_code == 200
    assert "RAG Admin Panel" in response.text
