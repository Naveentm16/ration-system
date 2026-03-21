from flask import Flask, render_template, request, jsonify, redirect, session
import sqlite3
from datetime import datetime, timedelta
import pandas as pd
import matplotlib.pyplot as plt
import os
import random

os.makedirs("static", exist_ok=True)

app = Flask(__name__)
app.secret_key = "secret123"

# ⏱ 5 MIN SESSION TIMEOUT
app.permanent_session_lifetime = timedelta(minutes=5)

def db():
    return sqlite3.connect("/tmp/ration.db")

# ================= DATABASE =================

conn = db()
conn.row_factory = sqlite3.Row

conn.execute("""
CREATE TABLE IF NOT EXISTS users(
id TEXT PRIMARY KEY,
name TEXT,
password TEXT
)
""")

# Default users
conn.execute("INSERT OR IGNORE INTO users VALUES ('101','Ravi','123')")
conn.execute("INSERT OR IGNORE INTO users VALUES ('102','Naveen','123')")
conn.execute("INSERT OR IGNORE INTO users VALUES ('103','Yalappa','123')")
conn.execute("INSERT OR IGNORE INTO users VALUES ('104','Kiran','123')")
conn.execute("INSERT OR IGNORE INTO users VALUES ('105','Vardhaman','123')")
conn.execute("INSERT OR IGNORE INTO users VALUES ('106','Pranath','123')")

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

# ================= SESSION MANAGEMENT =================

@app.before_request
def session_management():
    session.modified = True

# ================= USER LOGIN =================

@app.route("/user_login", methods=["GET","POST"])
def user_login():
    if request.method == "POST":
        id = request.form["id"]
        password = request.form["password"]

        conn = db()
        user = conn.execute(
            "SELECT * FROM users WHERE id=? AND password=?",
            (id, password)
        ).fetchone()

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
    conn = db()
    user = conn.execute("SELECT name FROM users WHERE id=?",(id,)).fetchone()
    return jsonify({"name": user[0] if user else ""})

# ================= SUBMIT =================

@app.route("/submit", methods=["POST"])
def submit():
    id = request.form["id"]
    name = request.form["name"]
    ration = request.form["ration"]
    amount = request.form["amount"]

    now = datetime.now()
    dt = now.strftime("%Y-%m-%d %H:%M:%S")
    tid = id + now.strftime("%Y%m%d%H%M%S")

    conn = db()
    conn.execute("INSERT INTO entries VALUES (?,?,?,?,?,?)",
                 (tid,id,name,ration,amount,dt))
    conn.commit()

    return "Submitted Successfully"

# ================= ADMIN LOGIN (OTP) =================

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        if request.form["username"]=="admin" and request.form["password"]=="1234":
            session.permanent = True

            # Generate OTP
            otp = str(random.randint(100000,999999))
            session["otp"] = otp

            print("Admin OTP:", otp)  # Check in Render logs

            return redirect("/verify_otp")

    return render_template("login.html")

# ================= OTP VERIFY =================

@app.route("/verify_otp", methods=["GET","POST"])
def verify_otp():
    if request.method == "POST":
        if request.form["otp"] == session.get("otp"):
            session["admin"] = True
            return redirect("/admin")
        else:
            return "Invalid OTP"

    return render_template("otp.html")

# ================= ADMIN =================

@app.route("/admin")
def admin():
    if "admin" not in session:
        return redirect("/login")

    conn = db()
    data = conn.execute("SELECT * FROM entries").fetchall()
    return render_template("admin.html", data=data)

# ================= DELETE =================

@app.route("/delete/<tid>")
def delete(tid):
    conn = db()
    conn.execute("DELETE FROM entries WHERE transaction_id=?", (tid,))
    conn.commit()
    return redirect("/admin")

# ================= REPORT =================

@app.route("/report")
def report():
    conn = db()
    df = pd.read_sql_query("SELECT * FROM entries", conn)

    if df.empty:
        return "No data available"

    summary = df.groupby("ration")["amount"].sum()

    os.makedirs("static", exist_ok=True)

    summary.plot(kind="bar")

    plt.title("Ration Report")
    plt.xlabel("Ration")
    plt.ylabel("Total Amount")

    plt.savefig("static/chart.png")
    plt.close()

    return render_template("report.html")

# ================= RUN =================

if __name__ == "__main__":
    app.run(debug=True)
