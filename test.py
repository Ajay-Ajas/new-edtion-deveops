from flask import Flask, jsonify, render_template, request, session, redirect
import sqlite3
from datetime import datetime, timedelta

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = "smartlibrary_secret_key"
DB = "library.db"

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
@app.route("/")
def home():
    return render_template("login.html")
@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect("/")
    return render_template("main.html")

if __name__ == "__main__":
    app.run(host="0.0.0.0",port=5000)
