from flask import Flask, render_template, request, redirect, session
import sqlite3
from datetime import datetime, timedelta
import pandas as pd
import matplotlib.pyplot as plt
import os
import random

# ================= CONFIG =================
app = Flask(__name__)
app.secret_key = "secret123"
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
    datetime TEXT,
    calculated INTEGER DEFAULT 0
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

# ================= USER DASHBOARD =================
@app.route("/")
def home():
    if "user" not in session:
        return redirect("/user_login")
    user_id = session["user"]
    conn = get_db()
    user = conn.execute("SELECT name FROM users WHERE id=?", (user_id,)).fetchone()
    entries = conn.execute("SELECT * FROM entries WHERE id=?", (user_id,)).fetchall()
    conn.close()
    return render_template("entry.html", entries=entries, user_name=user["name"])

# ================= MULTIPLE ENTRIES SUBMISSION =================
@app.route("/submit", methods=["POST"])
def submit():
    if "user" not in session:
        return redirect("/user_login")
    id = session["user"]
    name = request.form["name"]

    rations = request.form.getlist("ration[]")
    amounts = request.form.getlist("amount[]")

    conn = get_db()
    now = datetime.now()
    for r, a in zip(rations, amounts):
        tid = id + now.strftime("%Y%m%d%H%M%S") + str(random.randint(100,999))
        dt = now.strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("INSERT INTO entries VALUES (?,?,?,?,?,?,0)",
                     (tid, id, name, r, float(a), dt))
    conn.commit()
    conn.close()
    return redirect("/")

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
        conn.execute("UPDATE entries SET ration=?, amount=?, datetime=? WHERE transaction_id=?",
                     (ration, amount, dt, tid))
        conn.commit()
        conn.close()
        return redirect("/")
    conn.close()
    return render_template("update_entry.html", entry=entry)

# ================= USER LOGOUT =================
@app.route("/user_logout")
def user_logout():
    session.pop("user", None)
    return redirect("/user_login")

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
    settlements = conn.execute("SELECT * FROM settlements ORDER BY month DESC").fetchall()
    conn.close()
    return render_template("admin.html", data=data, settlements=settlements)

# ================= ADMIN LOGOUT =================
@app.route("/admin_logout")
def admin_logout():
    session.pop("admin", None)
    return redirect("/login")

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

# ================= CALCULATE MONTHLY SETTLEMENT =================
@app.route("/calculate_monthly", methods=["GET"])
def calculate_monthly():
    if "admin" not in session:
        return redirect("/login")
    month = request.args.get("month")  # YYYY-MM
    if not month:
        return "Please select a month"

    conn = get_db()
    df = pd.read_sql_query(
        "SELECT transaction_id, id, name, ration, amount FROM entries "
        "WHERE strftime('%Y-%m', datetime)=? AND calculated=0",
        conn, params=(month,)
    )

    if df.empty:
        conn.close()
        return f"No new transactions to calculate for {month}"

    # Total per user
    user_totals = df.groupby(["id","name"])["amount"].sum().reset_index()
    total_amount = user_totals["amount"].sum()
    num_users = len(user_totals)
    average = total_amount / num_users

    # Balance calculation
    user_totals["balance"] = user_totals["amount"] - average

    # Redistribute extra/less
    positives = user_totals[user_totals["balance"] > 0].copy()
    negatives = user_totals[user_totals["balance"] < 0].copy()
    total_positive = positives["balance"].sum()
    total_negative = -negatives["balance"].sum()

    if total_positive > 0 and total_negative > 0:
        for i, neg in negatives.iterrows():
            for j, pos in positives.iterrows():
                share = min(pos["balance"], -neg["balance"] * pos["balance"]/total_positive)
                user_totals.loc[user_totals["id"]==neg["id"], "balance"] += share
                user_totals.loc[user_totals["id"]==pos["id"], "balance"] -= share

    # Save settlement
    conn.execute("""
        INSERT OR REPLACE INTO settlements (month, total_amount, per_person, is_settled)
        VALUES (?,?,?,0)
    """, (month, total_amount, average))
    # Mark transactions as calculated
    conn.execute("UPDATE entries SET calculated=1 WHERE strftime('%Y-%m', datetime)=?", (month,))
    conn.commit()
    conn.close()

    return render_template("monthly_settlement.html",
                           month=month,
                           df=user_totals.to_dict(orient="records"),
                           total=total_amount,
                           per_person=average)

# ================= MARK MONTH AS SETTLED =================
@app.route("/settle_month/<month>")
def settle_month(month):
    if "admin" not in session:
        return redirect("/login")
    conn = get_db()
    conn.execute("UPDATE settlements SET is_settled=1 WHERE month=?", (month,))
    conn.commit()
    conn.close()
    return redirect("/admin")

# ================= CANCEL SETTLEMENT =================
@app.route("/cancel_settlement/<month>")
def cancel_settlement(month):
    if "admin" not in session:
        return redirect("/login")
    conn = get_db()
    # Reset settlement
    conn.execute("UPDATE settlements SET is_settled=0 WHERE month=?", (month,))
    # Reset transactions as not calculated
    conn.execute("UPDATE entries SET calculated=0 WHERE strftime('%Y-%m', datetime)=?", (month,))
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

# ================= RUN APP =================
if __name__ == "__main__":
    app.run(debug=True)
