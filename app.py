# app.py
from flask import Flask, render_template, request, jsonify, redirect, session
import sqlite3
from datetime import datetime, timedelta
import pandas as pd
import matplotlib.pyplot as plt
import os

# ================= CONFIG =================

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev_secret")  # Use env variable in production
app.permanent_session_lifetime = timedelta(minutes=5)  # 5-minute session timeout

os.makedirs("static", exist_ok=True)  # for charts

DB_PATH = "ration.db"

# ================= DATABASE =================

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# Initialize tables and default users
conn = get_db()
conn.execute("""
CREATE TABLE IF NOT EXISTS users(
    id TEXT PRIMARY KEY,
    name TEXT,
    password TEXT
)
""")

default_users = [
    ('101','Ravi','123'),
    ('102','Naveen','123'),
    ('103','Yalappa','123'),
    ('104','Kiran','123'),
    ('105','Vardhaman','123'),
    ('106','Pranath','123')
]

conn.executemany("INSERT OR IGNORE INTO users VALUES (?,?,?)", default_users)

conn.execute("""
CREATE TABLE IF NOT EXISTS entries(
    transaction_id TEXT PRIMARY KEY,
    id TEXT,
    name TEXT,
    ration TEXT,
    amount REAL,
    datetime TEXT
)
""")
conn.commit()
conn.close()

# ================= SESSION MANAGEMENT =================

@app.before_request
def session_management():
    session.modified = True  # refresh session expiry on activity

# ================= USER LOGIN =================

@app.route("/user_login", methods=["GET","POST"])
def user_login():
    if request.method == "POST":
        id = request.form["id"]
        password = request.form["password"]

        conn = get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE id=? AND password=?",
            (id, password)
        ).fetchone()
        conn.close()

        if user:
            session.permanent = True
            session["user"] = id
            return redirect("/")
        return "Invalid ID or Password"

    return render_template("user_login.html")

# ================= HOME =================

@app.route("/")
def home():
    if "user" not in session:
        return redirect("/user_login")
    return render_template("entry.html")

# ================= FETCH USER =================

@app.route("/get_user/<id>")
def get_user(id):
    conn = get_db()
    user = conn.execute("SELECT name FROM users WHERE id=?",(id,)).fetchone()
    conn.close()
    return jsonify({"name": user[0] if user else ""})

# ================= SUBMIT =================

@app.route("/submit", methods=["POST"])
def submit():
    id = request.form["id"]
    name = request.form["name"]
    ration = request.form["ration"]
    amount = float(request.form["amount"])

    now = datetime.now()
    dt = now.strftime("%Y-%m-%d %H:%M:%S")
    tid = id + now.strftime("%Y%m%d%H%M%S")

    conn = get_db()
    conn.execute("INSERT INTO entries VALUES (?,?,?,?,?,?)",
                 (tid,id,name,ration,amount,dt))
    conn.commit()
    conn.close()

    return "Submitted Successfully"

# ================= ADMIN LOGIN =================

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        if username == "admin" and password == "1234":
            session.permanent = True
            session["admin"] = True
            return redirect("/admin")
        else:
            return "Invalid username or password"

    return render_template("login.html")

# ================= ADMIN =================

@app.route("/admin")
def admin():
    if "admin" not in session:
        return redirect("/login")

    conn = get_db()
    data = conn.execute("SELECT * FROM entries").fetchall()
    conn.close()

    return render_template("admin.html", data=data)

# ================= DELETE ENTRY =================

@app.route("/delete/<tid>")
def delete(tid):
    if "admin" not in session:
        return redirect("/login")

    conn = get_db()
    conn.execute("DELETE FROM entries WHERE transaction_id=?", (tid,))
    conn.commit()
    conn.close()
    return redirect("/admin")

# ================= REPORT =================

@app.route("/report")
def report():
    if "admin" not in session:
        return redirect("/login")

    conn = get_db()
    df = pd.read_sql_query("SELECT * FROM entries", conn)
    conn.close()

    if df.empty:
        return "No data available"

    summary = df.groupby("ration")["amount"].sum()

    plt.figure(figsize=(8,5))
    summary.plot(kind="bar")
    plt.title("Ration Report")
    plt.xlabel("Ration")
    plt.ylabel("Total Amount")
    plt.tight_layout()

    chart_path = os.path.join("static", "chart.png")
    plt.savefig(chart_path)
    plt.close()

    return render_template("report.html", chart_path=chart_path)

# ================= RUN =================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
