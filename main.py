import os, sqlite3, secrets, hashlib, hmac
from contextlib import contextmanager
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel, Field

from fastapi.middleware.cors import CORSMiddleware
app = FastAPI(title="Switch-Shop")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET","POST"], allow_headers=["Authorization","Content-Type"])
@contextmanager
def db():
    c = sqlite3.connect(os.getenv("DB_PATH", "shop.db"))
    c.row_factory = sqlite3.Row
    try:
        with c:
            yield c
    finally:
        c.close()

with db() as c:
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT UNIQUE, salt TEXT, password TEXT, balance INTEGER DEFAULT 1000);
    CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, uid INTEGER);
    CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY, uid INTEGER, product TEXT, price INTEGER);
    CREATE TABLE IF NOT EXISTS cart(uid INTEGER, product TEXT, PRIMARY KEY(uid,product));
    """)

CATALOG = {"demo": {"name":"Demo item","price":100}}
class Credentials(BaseModel):
    name: str = Field(min_length=3,max_length=40)
    password: str = Field(min_length=8,max_length=128)

def digest(password,salt):
    return hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()

def user(c, authorization):
    if not authorization.startswith("Bearer "):
        raise HTTPException(401,"Login required")
    row=c.execute("SELECT uid FROM sessions WHERE token=?",(hashlib.sha256(authorization[7:].encode()).hexdigest(),)).fetchone()
    if not row: raise HTTPException(401,"Invalid session")
    return row["uid"]

@app.get("/")
def health(): return {"status":"ok","mode":"demo"}

@app.post("/register")
def register(body: Credentials):
    salt=secrets.token_hex(16)
    try:
        with db() as c:
            c.execute("INSERT INTO users(name,salt,password) VALUES(?,?,?)",(body.name,salt,digest(body.password,salt)))
    except sqlite3.IntegrityError:
        raise HTTPException(409,"Username taken")
    return {"ok":True}

@app.post("/login")
def login(body: Credentials):
    with db() as c:
        row=c.execute("SELECT * FROM users WHERE name=?",(body.name,)).fetchone()
        if not row or not hmac.compare_digest(row["password"],digest(body.password,row["salt"])):
            raise HTTPException(401,"Invalid credentials")
        token=secrets.token_urlsafe(32)
        c.execute("INSERT INTO sessions VALUES(?,?)",(hashlib.sha256(token.encode()).hexdigest(),row["id"]))
    return {"token":token}

@app.get("/catalog")
def catalog(): return CATALOG

@app.get("/balance")
def balance(authorization: str=Header(default="")):
    with db() as c:
        uid=user(c,authorization)
        return {"demo_credits":c.execute("SELECT balance FROM users WHERE id=?",(uid,)).fetchone()[0]}

@app.post("/cart/{product}")
def add(product:str,authorization:str=Header(default="")):
    if product not in CATALOG: raise HTTPException(404,"Unknown product")
    with db() as c:
        c.execute("INSERT OR IGNORE INTO cart VALUES(?,?)",(user(c,authorization),product))
    return {"ok":True}

@app.get("/cart")
def cart(authorization:str=Header(default="")):
    with db() as c:
        return [r[0] for r in c.execute("SELECT product FROM cart WHERE uid=?",(user(c,authorization),))]

@app.post("/checkout")
def checkout(authorization:str=Header(default="")):
    with db() as c:
        c.execute("BEGIN IMMEDIATE")
        uid=user(c,authorization)
        items=[r[0] for r in c.execute("SELECT product FROM cart WHERE uid=?",(uid,))]
        if not items: raise HTTPException(400,"Empty cart")
        total=sum(CATALOG[p]["price"] for p in items)
        if not c.execute("UPDATE users SET balance=balance-? WHERE id=? AND balance>=?",(total,uid,total)).rowcount:
            raise HTTPException(400,"Insufficient demo credits")
        c.executemany("INSERT INTO orders(uid,product,price) VALUES(?,?,?)",[(uid,p,CATALOG[p]["price"]) for p in items])
        c.execute("DELETE FROM cart WHERE uid=?",(uid,))
    return {"ok":True,"spent_demo_credits":total}

@app.get("/orders")
def orders(authorization:str=Header(default="")):
    with db() as c:
        return [dict(r) for r in c.execute("SELECT id,product,price FROM orders WHERE uid=?",(user(c,authorization),))]
