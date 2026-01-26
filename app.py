from flask import Flask, jsonify, render_template, request, session, redirect
import sqlite3
from datetime import datetime, timedelta

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = "smartlibrary_secret_key"
DB = "library.db"

# =========================
# SINGLETON : DATABASE
# =========================
class Database:
    _instance = None

    def __new__(cls, path):
        if cls._instance is None:
            cls._instance = super(Database, cls).__new__(cls)
            cls._instance.path = path
        return cls._instance

    def connect(self):
        return sqlite3.connect(self.path)

db = Database(DB)

# =========================
# USER CLASS
# =========================
class User:
    def __init__(self, user_id, name, role, department, year):
        self.user_id = user_id
        self.name = name
        self.role = role
        self.department = department
        self.year = year

    def to_dict(self):
        return {
            "id": self.user_id,
            "name": self.name,
            "role": self.role,
            "department": self.department,
            "year": self.year
        }

# =========================
# SINGLETON : LOGIN SERVICE
# =========================
class LoginService:
    _instance = None

    def __new__(cls, db):
        if cls._instance is None:
            cls._instance = super(LoginService, cls).__new__(cls)
            cls._instance.db = db
        return cls._instance

    def authenticate(self, user_id, password, role):
        con = self.db.connect()
        cur = con.cursor()
        cur.execute("""
            SELECT user_id, name, role, department, year
            FROM users
            WHERE user_id=? AND password=? AND role=?
        """, (user_id, password, role))
        row = cur.fetchone()
        con.close()
        if not row:
            return None
        return User(row[0], row[1], row[2], row[3], row[4])

login_service = LoginService(db)

# =========================
# BOOK COPY SERVICE
# =========================
class BookCopyService:
    def __init__(self, db):
        self.db = db

    def get_by_qr(self, qr_code):
        con = self.db.connect()
        cur = con.cursor()
        cur.execute("SELECT copy_id, book_id, status FROM book_copies WHERE qr_code=?", (qr_code,))
        row = cur.fetchone()
        con.close()
        return row

    def mark_borrowed(self, copy_id):
        con = self.db.connect()
        cur = con.cursor()
        cur.execute("UPDATE book_copies SET status='borrowed' WHERE copy_id=?", (copy_id,))
        con.commit()
        con.close()

copy_service = BookCopyService(db)

# =========================
# FACTORY : BORROW
# =========================
class BorrowBase:
    def create_borrow(self, user_id, copy_id, book_id):
        pass

class NormalBorrow(BorrowBase):
    def __init__(self, db):
        self.db = db

    def create_borrow(self, user_id, copy_id, book_id):
        now = datetime.now()
        return_by = now + timedelta(days=7)
        con = self.db.connect()
        cur = con.cursor()
        cur.execute("""
            INSERT INTO borrows (user_id, copy_id, borrowed_at, return_by)
            VALUES (?, ?, ?, ?)
        """, (user_id, copy_id, now, return_by))
        con.commit()
        con.close()

class BorrowFactory:
    @staticmethod
    def get_borrow_service(db):
        return NormalBorrow(db)

borrow_service = BorrowFactory.get_borrow_service(db)

# =========================
# FACTORY : PREBOOK
# =========================
class PrebookService:
    def __init__(self, db):
        self.db = db

    def prebook(self, user_id, role, book_id):
        con = self.db.connect()
        cur = con.cursor()

        max_prebook = 1 if role == "student" else 2
        cur.execute("SELECT COUNT(*) FROM borrow_requests WHERE user_id=? AND status='prebooked'", (user_id,))
        if cur.fetchone()[0] >= max_prebook:
            con.close()
            return {"error": "Prebook limit reached"}

        cur.execute("SELECT copy_id FROM book_copies WHERE book_id=? AND status='available' LIMIT 1", (book_id,))
        row = cur.fetchone()
        if not row:
            con.close()
            return {"error": "No copy available"}

        copy_id = row[0]
        now = datetime.now()
        expires_at = now + timedelta(hours=1)

        cur.execute("UPDATE book_copies SET status='prebooked' WHERE copy_id=?", (copy_id,))
        cur.execute("""
            INSERT INTO borrow_requests (user_id, copy_id, request_time, expires_at, status)
            VALUES (?, ?, ?, ?, 'prebooked')
        """, (user_id, copy_id, now, expires_at))

        con.commit()
        con.close()
        return {"status": "prebooked", "copy_id": copy_id, "expires_at": expires_at.isoformat()}

class StudentPrebook:
    def __init__(self, db):
        self.service = PrebookService(db)
    def prebook(self, user_id, role, book_id):
        return self.service.prebook(user_id, role, book_id)

class StaffPrebook:
    def __init__(self, db):
        self.service = PrebookService(db)
    def prebook(self, user_id, role, book_id):
        return self.service.prebook(user_id, role, book_id)

class PrebookFactory:
    @staticmethod
    def get_service(db, role):
        return StudentPrebook(db) if role == "student" else StaffPrebook(db)

# =========================
# PAGE ROUTES
# =========================
@app.route("/")
def home():
    return render_template("login.html")

@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect("/")
    return render_template("main.html")

@app.route("/borrow")
def borrow_page():
    if "user" not in session:
        return redirect("/")
    return render_template("borrow.html")

# =========================
# AUTH & SESSION
# =========================
@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.json
    user = login_service.authenticate(data["id"], data["password"], data["role"])
    if not user:
        return jsonify({"status": "fail"}), 401
    session["user"] = user.to_dict()
    return jsonify({"status": "success", "user": user.to_dict()})

@app.route("/api/me")
def api_me():
    if "user" not in session:
        return jsonify({"error": "Not logged in"}), 401
    return jsonify(session["user"])

# =========================
# BOOK APIS (Dashboard)
# =========================
@app.route("/api/books")
def get_books():
    con = db.connect()
    cur = con.cursor()
    cur.execute("SELECT id, title, available_stock, cover FROM books")
    rows = cur.fetchall()
    con.close()
    return jsonify([{
        "id": r[0],
        "title": r[1],
        "available": r[2],
        "cover": f"/static/covers/{r[3]}"
    } for r in rows])

@app.route("/api/book/<int:bid>")
def get_book(bid):
    con = db.connect()
    cur = con.cursor()
    cur.execute("SELECT title, author, description, available_stock, cover FROM books WHERE id=?", (bid,))
    r = cur.fetchone()
    con.close()
    return jsonify({
        "title": r[0],
        "author": r[1],
        "description": r[2],
        "available": r[3],
        "cover": f"/static/covers/{r[4]}"
    })

@app.route("/api/book-by-qr/<qr>")
def book_by_qr(qr):
    con = db.connect()
    cur = con.cursor()
    cur.execute("""
        SELECT b.title FROM book_copies bc
        JOIN books b ON bc.book_id=b.id
        WHERE bc.qr_code=?
    """, (qr,))
    r = cur.fetchone()
    con.close()
    if not r:
        return jsonify({"error": "Invalid QR"}), 404
    return jsonify({"title": r[0]})

# =========================
# PREBOOK & BORROW
# =========================
@app.route("/api/prebook/<int:book_id>", methods=["POST"])
def api_prebook(book_id):
    if "user" not in session:
        return jsonify({"error": "Not logged in"}), 401
    role = session["user"]["role"]
    user_id = session["user"]["id"]
    service = PrebookFactory.get_service(db, role)
    return jsonify(service.prebook(user_id, role, book_id))

@app.route("/api/borrow", methods=["POST"])
def api_borrow():
    if "user" not in session:
        return jsonify({"error": "Not logged in"}), 401

    qr_code = request.json.get("qr_code")
    user_id = session["user"]["id"]

    copy = copy_service.get_by_qr(qr_code)
    if not copy:
        return jsonify({"error": "Invalid QR"}), 400

    copy_id, book_id, _ = copy
    borrow_service.create_borrow(user_id, copy_id, book_id)
    copy_service.mark_borrowed(copy_id)

    return jsonify({"status": "borrowed"})

if __name__ == "__main__":
    app.run(debug=True)
