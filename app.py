from flask import Flask, render_template, request, jsonify, redirect, session
import sqlite3
from datetime import datetime
import pandas as pd
import matplotlib.pyplot as plt

app = Flask(__name__)
app.secret_key = "secret123"

def db():
    return sqlite3.connect("ration.db")

conn = db()
conn.execute("CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, name TEXT)")
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

@app.route("/")
def home():
    return render_template("entry.html")

@app.route("/get_user/<id>")
def get_user(id):
    conn = db()
    user = conn.execute("SELECT name FROM users WHERE id=?",(id,)).fetchone()
    return jsonify({"name": user[0] if user else ""})

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

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        if request.form["username"]=="admin" and request.form["password"]=="1234":
            session["admin"]=True
            return redirect("/admin")
    return render_template("login.html")

@app.route("/admin")
def admin():
    if "admin" not in session:
        return redirect("/login")
    conn = db()
    data = conn.execute("SELECT * FROM entries").fetchall()
    return render_template("admin.html", data=data)

@app.route("/delete/<tid>")
def delete(tid):
    conn = db()
    conn.execute("DELETE FROM entries WHERE transaction_id=?",(tid,))
    conn.commit()
    return redirect("/admin")

@app.route("/report")
def report():
    conn = db()
    df = pd.read_sql_query("SELECT * FROM entries", conn)

    if df.empty:
        return "No data available to generate report"

    summary = df.groupby("ration")["amount"].sum()

    import os
    os.makedirs("static", exist_ok=True)

    summary.plot(kind="bar")

    plt.title("Ration Report")
    plt.xlabel("Ration")
    plt.ylabel("Total Amount")

    plt.savefig("static/chart.png")
    plt.close()

    return render_template("report.html")
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
