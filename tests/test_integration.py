import pytest
from app import app


# =========================================
# Helper for readable output
# =========================================
def log_success(operation, layer):
    print("\n" + "_"*70)
    print(f" SUCCESS: {operation}")
    print(f" CONTROLLER/API: {layer}")
    print("_"*70)


@pytest.fixture
def client():
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test_secret"

    with app.test_client() as client:
        yield client


# ======================
# INTEGRATION TESTS
# ======================

def test_login_required(client):
    response = client.get("/api/me")

    log_success("Unauthorized Access Blocked", "/api/me")

    assert response.status_code == 401


def test_login_api_invalid(client):
    response = client.post("/api/login", json={
        "id": "wrong",
        "password": "wrong",
        "role": "student"
    })

    log_success("Invalid Login API Handling", "/api/login")

    assert response.status_code == 401


def test_session_flow(client):
    with client.session_transaction() as sess:
        sess["user"] = {"id": "u1", "role": "student"}

    response = client.get("/api/me")

    log_success("Session Authentication Flow", "/api/me")

    assert response.status_code == 200
    assert response.json["id"] == "u1"


def test_books_endpoint(client):
    response = client.get("/api/books")

    log_success("Books Retrieval Endpoint", "/api/books")

    assert response.status_code == 200
    assert isinstance(response.json, list)
