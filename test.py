from flask import Flask, jsonify, request, session, redirect, render_template_string
import sqlite3

app = Flask(__name__)
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
# LOGIN PAGE
# =========================
@app.route("/", methods=["GET"])
def login_page():
    return render_template_string("""
        <h2>Login</h2>
        <form onsubmit="login(event)">
            <input id="uid" placeholder="User ID"><br><br>
            <input id="pwd" type="password" placeholder="Password"><br><br>
            <select id="role">
                <option value="student">Student</option>
                <option value="staff">Staff</option>
            </select><br><br>
            <button type="submit">Login</button>
        </form>

        <p id="msg" style="color:red;"></p>

        <script>
        function login(e){
            e.preventDefault();

            fetch("/api/login", {
                method: "POST",
                headers: {"Content-Type":"application/json"},
                body: JSON.stringify({
                    id: document.getElementById("uid").value,
                    password: document.getElementById("pwd").value,
                    role: document.getElementById("role").value
                })
            })
            .then(res => {
                if(!res.ok) throw new Error();
                return res.json();
            })
            .then(data => {
                window.location.href = "/dashboard";
            })
            .catch(err => {
                document.getElementById("msg").innerText = "Invalid Login!";
            });
        }
        </script>
    """)

# =========================
# DASHBOARD PAGE
# =========================
@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect("/")

    return render_template_string("""
        <h2>Dashboard</h2>
        <div id="user"></div>

        <script>
        fetch("/api/me")
        .then(res => res.json())
        .then(data => {
            document.getElementById("user").innerHTML =
                "<p>ID: " + data.id + "</p>" +
                "<p>Name: " + data.name + "</p>" +
                "<p>Role: " + data.role + "</p>" +
                "<p>Department: " + data.department + "</p>" +
                "<p>Year: " + data.year + "</p>";
        });
        </script>
    """)

# =========================
# LOGIN API
# =========================
@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.json
    user = login_service.authenticate(data["id"], data["password"], data["role"])

    if not user:
        return jsonify({"status": "fail"}), 401

    session["user"] = user.to_dict()
    return jsonify({"status": "success"})

# =========================
# GET CURRENT USER
# =========================
@app.route("/api/me")
def api_me():
    if "user" not in session:
        return jsonify({"error": "Not logged in"}), 401
    return jsonify(session["user"])

# =========================
# RUN
# =========================
if __name__ == "__main__":
    app.run(debug=True)
