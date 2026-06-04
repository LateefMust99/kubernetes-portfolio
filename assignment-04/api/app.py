import os, time
import psycopg2
from flask import Flask, request, jsonify

app = Flask(__name__)

DB_HOST = os.environ.get("DB_HOST", "db")
DB_USER = os.environ.get("DB_USER", "cohort")
DB_PASS = os.environ.get("DB_PASS", "cohort")
DB_NAME = os.environ.get("DB_NAME", "cohort")


def connect():
    for _ in range(30):
        try:
            return psycopg2.connect(
                host=DB_HOST, user=DB_USER, password=DB_PASS, dbname=DB_NAME
            )
        except psycopg2.OperationalError:
            time.sleep(1)
    raise RuntimeError("db never came up")


@app.before_request
def ensure_schema():
    if getattr(app, "_ready", False):
        return
    with connect() as c, c.cursor() as cur:
        cur.execute(
            "CREATE TABLE IF NOT EXISTS notes (id SERIAL PRIMARY KEY, body TEXT NOT NULL)"
        )
        c.commit()
    app._ready = True


@app.get("/notes")
def list_notes():
    with connect() as c, c.cursor() as cur:
        cur.execute("SELECT id, body FROM notes ORDER BY id")
        return jsonify([{"id": i, "body": b} for i, b in cur.fetchall()])


@app.post("/notes")
def add_note():
    body = request.json.get("body", "")
    with connect() as c, c.cursor() as cur:
        cur.execute("INSERT INTO notes (body) VALUES (%s) RETURNING id", (body,))
        c.commit()
        return jsonify({"id": cur.fetchone()[0], "body": body}), 201


@app.get("/healthz")
def healthz():
    return ("ok", 200)