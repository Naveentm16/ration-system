# app.py
from flask import Flask, render_template, request, jsonify, redirect, session
import sqlite3
from datetime import datetime, timedelta
import pandas as pd
import matplotlib.pyplot as plt
import os

# ================= CONFIG =================

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev_secret")
app.permanent_session_lifetime = timedelta(minutes=5)

os.makedirs("static", exist_ok=True)

DB_PATH = "ration.db"

# ================= DATABASE =================

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# Initialize tables
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

conn.execute("""
CREATE TABLE IF NOT EXISTS settlements (
    month TEXT PRIMARY KEY,
    total_amount REAL,
    per_person REAL,
    is_settled INTEGER DEFAULT 0
)
""")
conn.commit()
conn.close()

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

    user_id = session["user"]
    conn = get_db()
    entries = conn.execute("SELECT * FROM entries WHERE id=?", (user_id,)).fetchall()
    conn.close()
    return render_template("entry.html", entries=entries)

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
    if "user" not in session:
        return redirect("/user_login")

    id = session["user"]
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

# ================= UPDATE ENTRY =================

@app.route("/update/<tid>", methods=["GET","POST"])
def update_entry(tid):
    if "user" not in session:
        return redirect("/user_login")

    user_id = session["user"]
    conn = get_db()
    entry = conn.execute("SELECT * FROM entries WHERE transaction_id=?", (tid,)).fetchone()

    if not entry:
        conn.close()
        return "Entry not found"

    if entry["id"] != user_id:
        conn.close()
        return "You are not allowed to update this entry"

    if request.method == "POST":
        ration = request.form["ration"]
        amount = float(request.form["amount"])
        dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        conn.execute("""
            UPDATE entries
            SET ration=?, amount=?, datetime=?
            WHERE transaction_id=?
        """, (ration, amount, dt, tid))
        conn.commit()
        conn.close()
        return "Entry updated successfully"

    conn.close()
    return render_template("update_entry.html", entry=entry)

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

# ================= ADMIN DASHBOARD =================

@app.route("/admin")
def admin():
    if "admin" not in session:
        return redirect("/login")

    conn = get_db()
    data = conn.execute("SELECT * FROM entries").fetchall()
    settlements = conn.execute("SELECT * FROM settlements").fetchall()
    conn.close()

    return render_template("admin.html", data=data, settlements=settlements)

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

# ================= MONTHLY SETTLEMENT =================

@app.route("/calculate_monthly/<month>")
def calculate_monthly(month):
    if "admin" not in session:
        return redirect("/login")

    conn = get_db()
    settled = conn.execute("SELECT is_settled FROM settlements WHERE month=?", (month,)).fetchone()
    if settled and settled["is_settled"] == 1:
        conn.close()
        return f"{month} is already settled."

    df = pd.read_sql_query(
        "SELECT id, name, SUM(amount) as paid FROM entries WHERE strftime('%Y-%m', datetime)=? GROUP BY id, name",
        conn,
        params=(month,)
    )

    if df.empty:
        conn.close()
        return f"No data for {month}"

    total_amount = df["paid"].sum()
    num_users = len(df)
    per_person_share = total_amount / num_users

    df["balance"] = df["paid"] - per_person_share

    # Redistribute extra if someone paid more
    extra = df.loc[df["balance"] > 0, "balance"].sum()
    owes = df.loc[df["balance"] < 0, "balance"].sum() * -1
    if extra > 0 and owes > 0:
        for idx, row in df.iterrows():
            if row["balance"] < 0:
                share = min(-row["balance"], extra * (-row["balance"]/owes))
                df.at[idx, "balance"] += share

    conn.execute("""
        INSERT OR REPLACE INTO settlements (month, total_amount, per_person, is_settled)
        VALUES (?,?,?,0)
    """, (month, total_amount, per_person_share))
    conn.commit()
    conn.close()

    return render_template("monthly_settlement.html",
                           month=month,
                           df=df.to_dict(orient="records"),
                           total=total_amount,
                           per_person=per_person_share)

# ================= MARK MONTH AS SETTLED =================

@app.route("/settle_month/<month>")
def settle_month(month):
    if "admin" not in session:
        return redirect("/login")

    conn = get_db()
    conn.execute("UPDATE settlements SET is_settled=1 WHERE month=?", (month,))
    conn.commit()
    conn.close()

    return f"Month {month} marked as settled."

# ================= RUN =================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
