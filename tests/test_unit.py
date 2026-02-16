import pytest
import sqlite3
import os
import app

TEST_DB = "test_library.db"


# =========================================
# Helper for clean readable output
# =========================================
def log_success(operation, cls):
    print("\n" + "_"*70)
    print(f" SUCCESS: {operation}")
    print(f" CLASS USED: {cls}")
    print("_"*70)


@pytest.fixture(scope="module", autouse=True)
def setup_environment():

    print("\nInitializing Test Environment...")
    print("Creating Test Database")
    print("Applying Singleton & Factory setup")

    # ✅ STEP 1: reset singleton instance
    app.Database._instance = None

    # ✅ STEP 2: create test DB
    con = sqlite3.connect(TEST_DB)
    cur = con.cursor()

    cur.executescript("""
    CREATE TABLE users(
        user_id TEXT,
        name TEXT,
        password TEXT,
        role TEXT,
        department TEXT,
        year TEXT
    );

    CREATE TABLE books(
        id INTEGER PRIMARY KEY,
        title TEXT,
        available_stock INTEGER,
        cover TEXT
    );

    CREATE TABLE book_copies(
        copy_id INTEGER PRIMARY KEY,
        book_id INTEGER,
        qr_code TEXT,
        status TEXT
    );

    CREATE TABLE borrow_requests(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        copy_id INTEGER,
        request_time TEXT,
        expires_at TEXT,
        status TEXT
    );
    """)

    cur.execute("INSERT INTO users VALUES('u1','Ajay','123','student','CSE','3')")
    cur.execute("INSERT INTO books VALUES(1,'Python',5,'cover.jpg')")
    cur.execute("INSERT INTO book_copies VALUES(1,1,'QR1','available')")

    con.commit()
    con.close()

    # ✅ STEP 3: replace GLOBAL db used everywhere
    app.db = app.Database(TEST_DB)

    # ✅ STEP 4: recreate services using SAME architecture
    app.login_service = app.LoginService(app.db)
    app.copy_service = app.BookCopyService(app.db)
    app.borrow_service = app.BorrowFactory.get_service(app.db)
    app.prebook_service = app.PrebookFactory.get_service(app.db, "student")

    yield

    print("\nCleaning up Test Database...")
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)


# ======================
# UNIT TESTS
# ======================

def test_login_success():
    user = app.login_service.authenticate("u1", "123", "student")
    log_success("Login Operation", "LoginService")

    assert user is not None
    assert user.name == "Ajay"


def test_login_fail():
    user = app.login_service.authenticate("u1", "wrong", "student")
    log_success("Invalid Login Handling", "LoginService")

    assert user is None


def test_get_book_copy():
    copy = app.copy_service.get_by_qr("QR1")
    log_success("Book Copy Lookup", "BookCopyService")

    assert copy is not None
    assert copy[0] == 1
    assert copy[2] == "available"


def test_prebook_success():
    result = app.prebook_service.prebook("u1", "student", 1)
    log_success("Prebook Operation", "PrebookService")

    assert result["status"] == "prebooked"
    assert result["copy_id"] == 1
