from flask import Flask, render_template, request, redirect, session, send_file
import psycopg2
import os, random
from datetime import datetime, timedelta
import pandas as pd
import matplotlib
matplotlib.use('Agg')

app = Flask(__name__)
app.secret_key = "secret123"
app.permanent_session_lifetime = timedelta(minutes=10)

# ================= DB CONNECTION =================
def get_db():
    db_url = os.environ.get("DATABASE_URL")

    # Fix Render URL issue
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgres://", 1)

    return psycopg2.connect(db_url, sslmode="require")

# ================= INIT =================
def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id TEXT PRIMARY KEY,
        name TEXT,
        password TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS entries(
        transaction_id TEXT PRIMARY KEY,
        id TEXT,
        name TEXT,
        ration TEXT,
        amount FLOAT,
        datetime TEXT,
        calculated INTEGER DEFAULT 0
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS settlement_details(
        id SERIAL PRIMARY KEY,
        settlement_id TEXT,
        payer TEXT,
        receiver TEXT,
        amount FLOAT,
        payer_status INTEGER DEFAULT 0,
        receiver_status INTEGER DEFAULT 0
    )
    """)

    users = [
        ('101','Ravi','123'),
        ('102','Naveen','123'),
        ('103','Yalappa','123'),
        ('104','Kiran','123')
    ]

    for u in users:
        cur.execute("""
        INSERT INTO users (id,name,password)
        VALUES (%s,%s,%s)
        ON CONFLICT (id) DO NOTHING
        """, u)

    conn.commit()
    cur.close()
    conn.close()

init_db()

# ================= USER LOGIN =================
@app.route("/user_login", methods=["GET","POST"])
def user_login():
    if request.method=="POST":
        conn=get_db()
        cur=conn.cursor()

        cur.execute("SELECT * FROM users WHERE id=%s AND password=%s",
                    (request.form["id"], request.form["password"]))
        user=cur.fetchone()

        cur.close()
        conn.close()

        if user:
            session["user"]=user[0]
            return redirect("/")

    return render_template("user_login.html")

# ================= HOME =================
@app.route("/")
def home():
    if "user" not in session:
        return redirect("/user_login")

    conn=get_db()
    cur=conn.cursor()

    cur.execute("SELECT name FROM users WHERE id=%s", (session["user"],))
    user=cur.fetchone()

    cur.execute("SELECT * FROM entries WHERE id=%s", (session["user"],))
    entries=cur.fetchall()

    cur.execute("SELECT settlement_id FROM settlement_details ORDER BY settlement_id DESC LIMIT 1")
    latest=cur.fetchone()

    cur.close()
    conn.close()

    latest_id = latest[0] if latest else None

    return render_template("entry.html",
                           entries=entries,
                           user_name=user[0],
                           latest_id=latest_id)

# ================= ADD ENTRY =================
@app.route("/submit", methods=["POST"])
def submit():
    conn=get_db()
    cur=conn.cursor()

    now=datetime.now()

    for r,a in zip(request.form.getlist("ration[]"), request.form.getlist("amount[]")):
        if r and a:
            tid=session["user"]+now.strftime("%Y%m%d%H%M%S")+str(random.randint(100,999))

            cur.execute("""
            INSERT INTO entries
            VALUES (%s,%s,%s,%s,%s,%s,0)
            """,(tid,session["user"],request.form["name"],r,float(a),
                 now.strftime("%Y-%m-%d %H:%M:%S")))

    conn.commit()
    cur.close()
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
    cur=conn.cursor()

    cur.execute("SELECT * FROM entries")
    data=cur.fetchall()

    cur.execute("SELECT * FROM users")
    users=cur.fetchall()

    cur.execute("SELECT DISTINCT settlement_id FROM settlement_details ORDER BY settlement_id DESC")
    settlements=cur.fetchall()

    cur.close()
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

    query = f"SELECT * FROM entries WHERE transaction_id IN ({','.join(['%s']*len(tids))})"
    df = pd.read_sql(query, conn, params=tids)

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
        if r["balance"]<0:
            owe[r["name"]]=-r["balance"]
        elif r["balance"]>0:
            receive[r["name"]]=r["balance"]

    sid=datetime.now().strftime("%Y%m%d%H%M%S")

    cur=conn.cursor()

    for d in list(owe.keys()):
        debt=owe[d]
        for c in list(receive.keys()):
            if debt==0: break

            pay=min(debt,receive[c])

            cur.execute("""
            INSERT INTO settlement_details
            (settlement_id,payer,receiver,amount)
            VALUES (%s,%s,%s,%s)
            """,(sid,d,c,round(pay,2)))

            debt-=pay
            receive[c]-=pay

            if receive[c]==0:
                del receive[c]

    update_query = f"UPDATE entries SET calculated=1 WHERE transaction_id IN ({','.join(['%s']*len(tids))})"
    cur.execute(update_query, tids)

    conn.commit()
    cur.close()
    conn.close()

    return redirect("/admin")

# ================= RUN =================
if __name__=="__main__":
    app.run()
