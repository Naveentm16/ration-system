from flask import Flask, render_template, request, redirect, session, send_file
import sqlite3, os, random
from datetime import datetime, timedelta
import pandas as pd
import matplotlib
matplotlib.use('Agg')

app = Flask(__name__)
app.secret_key = "secret123"
app.permanent_session_lifetime = timedelta(minutes=10)

# ✅ DATABASE FIX (NO /tmp)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE_DIR, "ration.db")

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

# ================= INIT =================
conn = get_db()

conn.execute("""CREATE TABLE IF NOT EXISTS users(
id TEXT PRIMARY KEY,
name TEXT,
password TEXT)""")

conn.execute("""CREATE TABLE IF NOT EXISTS entries(
transaction_id TEXT PRIMARY KEY,
id TEXT,
name TEXT,
ration TEXT,
amount REAL,
datetime TEXT,
calculated INTEGER DEFAULT 0)""")

conn.execute("""CREATE TABLE IF NOT EXISTS settlement_details(
id INTEGER PRIMARY KEY AUTOINCREMENT,
settlement_id TEXT,
payer TEXT,
receiver TEXT,
amount REAL,
payer_status INTEGER DEFAULT 0,
receiver_status INTEGER DEFAULT 0)""")

users=[('101','Ravi','123'),('102','Naveen','123'),
       ('103','Yalappa','123'),('104','Kiran','123')]

conn.executemany("INSERT OR IGNORE INTO users VALUES (?,?,?)", users)
conn.commit()
conn.close()

# ================= USER LOGIN =================
@app.route("/user_login", methods=["GET","POST"])
def user_login():
    if request.method=="POST":
        conn=get_db()
        user=conn.execute("SELECT * FROM users WHERE id=? AND password=?",
                          (request.form["id"],request.form["password"])).fetchone()
        conn.close()
        if user:
            session["user"]=user["id"]
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

    latest=conn.execute("SELECT settlement_id FROM settlement_details ORDER BY settlement_id DESC LIMIT 1").fetchone()
    latest_id = latest["settlement_id"] if latest else None

    conn.close()

    return render_template("entry.html",
                           entries=entries,
                           user_name=user["name"],
                           latest_id=latest_id)

# ================= ADD ENTRY =================
@app.route("/submit", methods=["POST"])
def submit():
    conn=get_db()
    now=datetime.now()

    for r,a in zip(request.form.getlist("ration[]"), request.form.getlist("amount[]")):
        if r and a:
            tid=session["user"]+now.strftime("%Y%m%d%H%M%S")+str(random.randint(100,999))
            conn.execute("INSERT INTO entries VALUES (?,?,?,?,?,?,0)",
                         (tid,session["user"],request.form["name"],r,float(a),
                          now.strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()
    return redirect("/")

# ================= ADMIN LOGIN =================
@app.route("/login", methods=["GET","POST"])
def login():
    if request.method=="POST":
        if request.form["username"]=="admin" and request.form["password"]=="1234":
            session["admin"]=True
            return redirect("/admin")
    return render_template("login.html")

# ================= ADMIN =================
@app.route("/admin")
def admin():
    if "admin" not in session:
        return redirect("/login")

    conn=get_db()
    data=conn.execute("SELECT * FROM entries").fetchall()
    users=conn.execute("SELECT * FROM users").fetchall()
    settlements=conn.execute("SELECT DISTINCT settlement_id FROM settlement_details").fetchall()
    conn.close()

    return render_template("admin.html",
                           data=data,
                           users=users,
                           settlements=settlements)

# ================= CALCULATE =================
@app.route("/calculate", methods=["POST"])
def calculate():
    tids=request.form.getlist("tids")
    users_sel=request.form.getlist("users")

    if not tids or not users_sel:
        return "Select transactions & users"

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

    owe,receive={},{}
    for _,r in merged.iterrows():
        if r["balance"]<0: owe[r["name"]]=-r["balance"]
        elif r["balance"]>0: receive[r["name"]]=r["balance"]

    sid=datetime.now().strftime("%Y%m%d%H%M%S")

    settlements_list=[]
    for d in list(owe.keys()):
        debt=owe[d]
        for c in list(receive.keys()):
            if debt==0: break
            pay=min(debt,receive[c])

            settlements_list.append({"from":d,"to":c,"amount":round(pay,2)})

            conn.execute("""INSERT INTO settlement_details
            (settlement_id,payer,receiver,amount)
            VALUES (?,?,?,?)""",(sid,d,c,round(pay,2)))

            debt-=pay
            receive[c]-=pay
            if receive[c]==0: del receive[c]

    conn.execute(f"UPDATE entries SET calculated=1 WHERE transaction_id IN ({','.join(['?']*len(tids))})", tids)

    conn.commit()
    conn.close()

    return render_template("monthly_settlement.html",
                           settlements=settlements_list,
                           month=sid)

# ================= RUN =================
if __name__=="__main__":
    app.run()
