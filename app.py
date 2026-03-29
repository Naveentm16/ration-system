from flask import Flask, render_template, request, redirect, session
import sqlite3
from datetime import datetime, timedelta
import pandas as pd
import random

app = Flask(__name__)
app.secret_key = "secret123"
app.permanent_session_lifetime = timedelta(minutes=5)

DB = "ration.db"

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

# ================= INIT =================
conn = get_db()

conn.execute("""
CREATE TABLE IF NOT EXISTS users(
id TEXT PRIMARY KEY,
name TEXT,
password TEXT)
""")

conn.execute("""
CREATE TABLE IF NOT EXISTS entries(
transaction_id TEXT PRIMARY KEY,
id TEXT,
name TEXT,
ration TEXT,
amount REAL,
datetime TEXT,
calculated INTEGER DEFAULT 0)
""")

conn.execute("""
CREATE TABLE IF NOT EXISTS settlements(
month TEXT PRIMARY KEY,
total_amount REAL,
per_person REAL)
""")

conn.execute("""
CREATE TABLE IF NOT EXISTS settlement_details(
id INTEGER PRIMARY KEY AUTOINCREMENT,
settlement_id TEXT,
payer TEXT,
receiver TEXT,
amount REAL,
payer_status INTEGER DEFAULT 0,
receiver_status INTEGER DEFAULT 0)
""")

users = [('101','Ravi','123'),('102','Naveen','123'),
         ('103','Yalappa','123'),('104','Kiran','123')]
conn.executemany("INSERT OR IGNORE INTO users VALUES (?,?,?)", users)

conn.commit()
conn.close()

# ================= USER LOGIN =================
@app.route("/user_login", methods=["GET","POST"])
def user_login():
    if request.method=="POST":
        id=request.form["id"]
        pw=request.form["password"]
        conn=get_db()
        user=conn.execute("SELECT * FROM users WHERE id=? AND password=?", (id,pw)).fetchone()
        conn.close()
        if user:
            session["user"]=id
            return redirect("/")
    return render_template("user_login.html")

# ================= HOME =================
@app.route("/")
def home():
    if "user" not in session:
        return redirect("/user_login")
    conn=get_db()
    user=conn.execute("SELECT name FROM users WHERE id=?", (session["user"],)).fetchone()
    entries=conn.execute("SELECT * FROM entries WHERE id=?", (session["user"],)).fetchall()
    conn.close()
    return render_template("entry.html", entries=entries, user_name=user["name"])

# ================= SUBMIT =================
@app.route("/submit", methods=["POST"])
def submit():
    conn=get_db()
    now=datetime.now()
    for r,a in zip(request.form.getlist("ration[]"), request.form.getlist("amount[]")):
        tid=session["user"]+now.strftime("%Y%m%d%H%M%S")+str(random.randint(100,999))
        conn.execute("INSERT INTO entries VALUES (?,?,?,?,?,?,0)",
                     (tid,session["user"],request.form["name"],r,float(a),
                      now.strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()
    return redirect("/")

# ================= ADMIN =================
@app.route("/login", methods=["GET","POST"])
def login():
    if request.method=="POST":
        if request.form["username"]=="admin" and request.form["password"]=="1234":
            session["admin"]=True
            return redirect("/admin")
    return render_template("login.html")

@app.route("/admin")
def admin():
    if "admin" not in session:
        return redirect("/login")
    conn=get_db()
    data=conn.execute("SELECT * FROM entries").fetchall()
    users=conn.execute("SELECT * FROM users").fetchall()
    details=conn.execute("SELECT * FROM settlement_details").fetchall()
    conn.close()
    return render_template("admin.html", data=data, users=users, details=details)

# ================= CALCULATION =================
@app.route("/calculate", methods=["POST"])
def calculate():
    tids=request.form.getlist("tids")
    users_sel=request.form.getlist("users")

    conn=get_db()

    df=pd.read_sql_query(
        f"SELECT * FROM entries WHERE transaction_id IN ({','.join(['?']*len(tids))})",
        conn, params=tids)

    all_users=pd.DataFrame({"id":users_sel})
    totals=df.groupby(["id","name"])["amount"].sum().reset_index()
    merged=pd.merge(all_users, totals, on="id", how="left")
    merged["name"]=merged["name"].fillna(merged["id"])
    merged["amount"]=merged["amount"].fillna(0)

    total=merged["amount"].sum()
    avg=total/len(merged)
    merged["balance"]=merged["amount"]-avg

    owe={}
    receive={}

    for _,r in merged.iterrows():
        if r["balance"]<0:
            owe[r["name"]]=-r["balance"]
        elif r["balance"]>0:
            receive[r["name"]]=r["balance"]

    settlement_id=datetime.now().strftime("%Y%m%d%H%M%S")

    for d in list(owe.keys()):
        debt=owe[d]
        for c in list(receive.keys()):
            if debt==0: break
            pay=min(debt,receive[c])
            conn.execute("""
            INSERT INTO settlement_details 
            (settlement_id,payer,receiver,amount)
            VALUES (?,?,?,?)""",(settlement_id,d,c,round(pay,2)))
            debt-=pay
            receive[c]-=pay
            if receive[c]==0: del receive[c]

    conn.execute(f"UPDATE entries SET calculated=1 WHERE transaction_id IN ({','.join(['?']*len(tids))})", tids)
    conn.commit()
    conn.close()

    return redirect("/admin")

# ================= USER SETTLEMENT =================
@app.route("/user_settlement/<sid>")
def user_settlement(sid):
    conn=get_db()
    user=conn.execute("SELECT name FROM users WHERE id=?", (session["user"],)).fetchone()
    name=user["name"]

    pay=conn.execute("SELECT * FROM settlement_details WHERE settlement_id=? AND payer=?", (sid,name)).fetchall()
    receive=conn.execute("SELECT * FROM settlement_details WHERE settlement_id=? AND receiver=?", (sid,name)).fetchall()

    conn.close()
    return render_template("user_settlement.html", pay=pay, receive=receive, name=name, sid=sid)

# ================= MARK =================
@app.route("/mark_paid/<int:id>")
def mark_paid(id):
    conn=get_db()
    user=conn.execute("SELECT name FROM users WHERE id=?", (session["user"],)).fetchone()
    conn.execute("UPDATE settlement_details SET payer_status=1 WHERE id=? AND payer=?", (id,user["name"]))
    conn.commit()
    conn.close()
    return redirect(request.referrer)

@app.route("/mark_received/<int:id>")
def mark_received(id):
    conn=get_db()
    user=conn.execute("SELECT name FROM users WHERE id=?", (session["user"],)).fetchone()
    conn.execute("UPDATE settlement_details SET receiver_status=1 WHERE id=? AND receiver=?", (id,user["name"]))
    conn.commit()
    conn.close()
    return redirect(request.referrer)

# ================= RUN =================
if __name__=="__main__":
    app.run(debug=True)
