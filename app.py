from flask import Flask, jsonify, render_template, request, session, redirect
import sqlite3
from datetime import datetime, timedelta
from prometheus_flask_exporter import PrometheusMetrics


app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = "smartlibrary_secret_key"
# =========================================================
# PROMETHEUS METRICS
# =========================================================
metrics = PrometheusMetrics(app)
metrics.info('smart_library_app', 'Application Info', version='1.0')

DB = "library.db"


# =========================================================
# MODEL LAYER
# =========================================================

class Database:
    _instance = None
    def __new__(cls, path):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.path = path
        return cls._instance
    def connect(self):
        return sqlite3.connect(self.path)

db = Database(DB)

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

class LoginService:
    _instance=None
    def __new__(cls, db):
        if cls._instance is None:
            cls._instance=super().__new__(cls)
            cls._instance.db=db
        return cls._instance
    def authenticate(self, user_id, password, role):
        con=db.connect()
        cur=con.cursor()
        cur.execute("""
            SELECT user_id,name,role,department,year
            FROM users WHERE user_id=? AND password=? AND role=?
        """,(user_id,password,role))
        row=cur.fetchone()
        con.close()
        return User(*row) if row else None

login_service=LoginService(db)

class BookCopyService:
    def __init__(self,db): self.db=db
    def get_by_qr(self,qr):
        con=db.connect()
        cur=con.cursor()
        cur.execute("SELECT copy_id,book_id,status FROM book_copies WHERE qr_code=?",(qr,))
        r=cur.fetchone()
        con.close()
        return r
    def mark_borrowed(self,copy_id):
        con=db.connect()
        cur=con.cursor()
        cur.execute("UPDATE book_copies SET status='borrowed' WHERE copy_id=?",(copy_id,))
        con.commit()
        con.close()

copy_service=BookCopyService(db)

class NormalBorrow:
    def __init__(self,db): self.db=db
    def create_borrow(self,user_id,copy_id,book_id):
        now=datetime.now()
        ret=now+timedelta(days=7)
        con=db.connect()
        cur=con.cursor()
        cur.execute("""
            INSERT INTO borrows (user_id,copy_id,borrowed_at,return_by)
            VALUES (?,?,?,?)
        """,(user_id,copy_id,now,ret))
        con.commit()
        con.close()

class BorrowFactory:
    @staticmethod
    def get_service(db): return NormalBorrow(db)

borrow_service=BorrowFactory.get_service(db)

class PrebookService:
    def __init__(self,db): self.db=db

    def expire_prebooks(self):
        now=datetime.now()
        con=db.connect()
        cur=con.cursor()
        cur.execute("""
            SELECT id,copy_id FROM borrow_requests
            WHERE status='prebooked' AND expires_at < ?
        """,(now,))
        for rid,copy_id in cur.fetchall():
            cur.execute("UPDATE borrow_requests SET status='expired' WHERE id=?",(rid,))
            cur.execute("UPDATE book_copies SET status='available' WHERE copy_id=?",(copy_id,))
            cur.execute("""
                UPDATE books SET available_stock=available_stock+1
                WHERE id=(SELECT book_id FROM book_copies WHERE copy_id=?)
            """,(copy_id,))
        con.commit()
        con.close()

    def prebook(self,user_id,role,book_id):
        self.expire_prebooks()
        con=db.connect()
        cur=con.cursor()

        max_pre=1 if role=="student" else 2
        cur.execute("""
            SELECT COUNT(*) FROM borrow_requests
            WHERE user_id=? AND status='prebooked'
        """,(user_id,))
        if cur.fetchone()[0]>=max_pre:
            con.close()
            return {"error":"Prebook limit reached"}

        cur.execute("""
            SELECT copy_id FROM book_copies
            WHERE book_id=? AND status='available' LIMIT 1
        """,(book_id,))
        row=cur.fetchone()
        if not row:
            con.close()
            return {"error":"No copy available"}

        copy_id=row[0]
        now=datetime.now()
        exp=now+timedelta(hours=1)

        cur.execute("UPDATE book_copies SET status='prebooked' WHERE copy_id=?",(copy_id,))
        cur.execute("""
            UPDATE books SET available_stock=available_stock-1
            WHERE id=? AND available_stock>0
        """,(book_id,))
        cur.execute("""
            INSERT INTO borrow_requests (user_id,copy_id,request_time,expires_at,status)
            VALUES (?,?,?,?, 'prebooked')
        """,(user_id,copy_id,now,exp))
        con.commit()
        con.close()

        return {"status":"prebooked","copy_id":copy_id,"expires_at":exp.isoformat()}

class PrebookFactory:
    @staticmethod
    def get_service(db, role):
        return PrebookService(db)

prebook_service = PrebookService(db)

# =========================================================
# VIEW
# =========================================================

@app.route("/")
def home(): return render_template("login.html")

@app.route("/dashboard")
def dashboard():
    if "user" not in session: return redirect("/")
    return render_template("main.html")

@app.route("/borrow")
def borrow_page():
    if "user" not in session: return redirect("/")
    return render_template("borrow.html")

@app.route("/detail")
def detail_page():
    if "user" not in session: return redirect("/")
    return render_template("detail.html")

# =========================================================
# CONTROLLER
# =========================================================

@app.route("/api/book-by-qr/<qr>")
def book_by_qr(qr):
    con = db.connect()
    cur = con.cursor()
    cur.execute("""
        SELECT b.title FROM book_copies bc
        JOIN books b ON bc.book_id=b.id
        WHERE bc.qr_code=?
    """,(qr,))
    r = cur.fetchone()
    con.close()

    if not r:
        return jsonify({"error":"Invalid QR"}),404

    return jsonify({"title": r[0]})

@app.route("/api/login",methods=["POST"])
def api_login():
    data=request.json
    user=login_service.authenticate(data["id"],data["password"],data["role"])
    if not user: return jsonify({"status":"fail"}),401
    session["user"]=user.to_dict()
    return jsonify({"status":"success","user":user.to_dict()})

@app.route("/api/me")
def api_me():
    if "user" not in session:
        return jsonify({"error":"Not logged in"}),401
    return jsonify(session["user"])

@app.route("/api/books")
def get_books():
    prebook_service.expire_prebooks()
    con=db.connect()
    cur=con.cursor()
    cur.execute("SELECT id,title,available_stock,cover FROM books")
    rows=cur.fetchall()
    con.close()
    return jsonify([{"id":r[0],"title":r[1],"available":r[2],"cover":f"/static/covers/{r[3]}"} for r in rows])

@app.route("/api/book/<int:bid>")
def get_book(bid):
    prebook_service.expire_prebooks()
    con=db.connect()
    cur=con.cursor()
    cur.execute("""
        SELECT title,author,description,available_stock,cover
        FROM books WHERE id=?
    """,(bid,))
    r=cur.fetchone()
    con.close()
    if not r: return jsonify({"error":"Not found"}),404
    return jsonify({"title":r[0],"author":r[1],"description":r[2],"available":r[3],"cover":f"/static/covers/{r[4]}"})

@app.route("/api/my-prebook/<int:book_id>")
def api_my_prebook(book_id):
    if "user" not in session: return jsonify({})
    prebook_service.expire_prebooks()
    user_id=session["user"]["id"]
    now=datetime.now()
    con=db.connect()
    cur=con.cursor()
    cur.execute("""
        SELECT bc.qr_code,br.expires_at
        FROM borrow_requests br
        JOIN book_copies bc ON br.copy_id=bc.copy_id
        WHERE br.user_id=? AND bc.book_id=? AND br.status='prebooked' AND br.expires_at>?
    """,(user_id,book_id,now))
    row=cur.fetchone()
    con.close()
    if not row: return jsonify({})
    exp=row[1]
    if isinstance(exp,str):
        exp=datetime.fromisoformat(exp)
    return jsonify({"qr":row[0],"expires_at":exp.isoformat()})

@app.route("/api/prebook/<int:book_id>",methods=["POST"])
def api_prebook(book_id):
    if "user" not in session:
        return jsonify({"error":"Not logged in"}),401
    role=session["user"]["role"]
    user_id=session["user"]["id"]
    result = prebook_service.prebook(user_id,role,book_id)
    if "error" in result:
        return jsonify(result),400
    return jsonify(result)

@app.route("/api/my-prebooks")
def api_my_prebooks():
    if "user" not in session:
        return jsonify([])

    prebook_service.expire_prebooks()

    user_id = session["user"]["id"]
    now = datetime.now()

    con = db.connect()
    cur = con.cursor()

    cur.execute("""
        SELECT b.title, bc.qr_code, br.expires_at
        FROM borrow_requests br
        JOIN book_copies bc ON br.copy_id = bc.copy_id
        JOIN books b ON bc.book_id = b.id
        WHERE br.user_id=? 
        AND br.status='prebooked'
        AND br.expires_at > ?
        ORDER BY br.expires_at ASC
    """, (user_id, now))

    rows = cur.fetchall()
    con.close()

    result = []
    for title, qr, exp in rows:
        if isinstance(exp, str):
            exp = datetime.fromisoformat(exp)
        result.append({
            "title": title,
            "qr": qr,
            "expires_at": exp.isoformat()
        })

    return jsonify(result)


@app.route("/api/borrow", methods=["POST"])
def api_borrow():
    if "user" not in session:
        return jsonify({"error":"Not logged in"}),401

    prebook_service.expire_prebooks()

    qr_code = request.json.get("qr_code")
    user_id = session["user"]["id"]

    copy = copy_service.get_by_qr(qr_code)
    if not copy:
        return jsonify({"error":"Invalid QR"}),400

    copy_id, book_id, status = copy

    con = db.connect()
    cur = con.cursor()

    # IMPORTANT: if book was NOT prebooked reduce stock now
    if status == "available":
        cur.execute("""
            UPDATE books
            SET available_stock = available_stock - 1
            WHERE id=? AND available_stock > 0
        """, (book_id,))

    # if prebook existed mark completed
    cur.execute("""
        UPDATE borrow_requests
        SET status='completed'
        WHERE copy_id=? AND user_id=? AND status='prebooked'
    """, (copy_id, user_id))

    con.commit()
    con.close()

    copy_service.mark_borrowed(copy_id)
    borrow_service.create_borrow(user_id, copy_id, book_id)

    return jsonify({"status":"borrowed"})

@app.route("/api/history")
def api_history():
    if "user" not in session:
        return jsonify({"error":"Not logged in"}),401
    user_id=session["user"]["id"]
    con=db.connect()
    cur=con.cursor()
    cur.execute("""
        SELECT b.title,bc.qr_code,br.borrowed_at,br.return_by,br.returned_at
        FROM borrows br
        JOIN book_copies bc ON br.copy_id=bc.copy_id
        JOIN books b ON bc.book_id=b.id
        WHERE br.user_id=?
        ORDER BY br.borrowed_at DESC
    """,(user_id,))
    rows=cur.fetchall()
    con.close()
    return jsonify(rows)

if __name__=="__main__":
    app.run(debug=True)
