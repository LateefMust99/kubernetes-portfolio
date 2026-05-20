import os, signal, sys
from flask import Flask

app = Flask(__name__)

@app.get("/")
def hello():
    return f"hello from {os.environ.get('STUDENT_NAME', 'anonymous')}\n"

@app.get("/healthz")
def healthz():
    return ("ok", 200)

def shutdown(*_):
    print("shutting down gracefully", flush=True)
    sys.exit(0)

signal.signal(signal.SIGTERM, shutdown)# test
