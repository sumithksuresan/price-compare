import os
import sqlite3
import uuid
import hashlib
import hmac
from datetime import datetime, timedelta
from functools import wraps

import jwt
from flask import Flask, request, jsonify, redirect, url_for, session
from authlib.integrations.flask_client import OAuth

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-prod")

JWT_SECRET = os.environ.get("JWT_SECRET", "jwt-secret-change-in-prod")
JWT_ALGORITHM = "HS256"
JWT_EXP_HOURS = 24

DB_PATH = os.environ.get("DB_PATH", "/data/auth.db")

# --- OAuth / SSO ---
oauth = OAuth(app)
google = oauth.register(
    name="google",
    client_id=os.environ.get("GOOGLE_CLIENT_ID", ""),
    client_secret=os.environ.get("GOOGLE_CLIENT_SECRET", ""),
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            name TEXT,
            password_hash TEXT,
            sso_provider TEXT,
            sso_id TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            last_login TEXT
        );
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            token TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
    """)
    conn.commit()
    conn.close()


def hash_password(password: str) -> str:
    salt = os.urandom(16).hex()
    h = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}:{h}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, h = stored.split(":", 1)
        return hmac.compare_digest(h, hashlib.sha256((salt + password).encode()).hexdigest())
    except Exception:
        return False


def make_token(user_id: str, email: str, name: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "name": name,
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXP_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def require_token(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify({"error": "Missing token"}), 401
        token = auth[7:]
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            request.user = payload
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401
        return f(*args, **kwargs)
    return decorated


# --- Routes ---

@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "auth"})


@app.route("/register", methods=["POST"])
def register():
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    name = (data.get("name") or email).strip()

    if not email or not password:
        return jsonify({"error": "email and password required"}), 400
    if len(password) < 6:
        return jsonify({"error": "password must be at least 6 characters"}), 400

    conn = get_db()
    try:
        existing = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if existing:
            return jsonify({"error": "email already registered"}), 409

        user_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO users (id, email, name, password_hash) VALUES (?, ?, ?, ?)",
            (user_id, email, name, hash_password(password)),
        )
        conn.commit()
        token = make_token(user_id, email, name)
        return jsonify({"token": token, "user": {"id": user_id, "email": email, "name": name}}), 201
    finally:
        conn.close()


@app.route("/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return jsonify({"error": "email and password required"}), 400

    conn = get_db()
    try:
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if not user or not verify_password(password, user["password_hash"] or ""):
            return jsonify({"error": "invalid credentials"}), 401

        conn.execute("UPDATE users SET last_login = ? WHERE id = ?", (datetime.utcnow().isoformat(), user["id"]))
        conn.commit()
        token = make_token(user["id"], user["email"], user["name"])
        return jsonify({"token": token, "user": {"id": user["id"], "email": user["email"], "name": user["name"]}})
    finally:
        conn.close()


@app.route("/sso/google")
def sso_google():
    redirect_uri = url_for("sso_google_callback", _external=True)
    return google.authorize_redirect(redirect_uri)


@app.route("/sso/google/callback")
def sso_google_callback():
    frontend_url = os.environ.get("FRONTEND_URL", "http://localhost")
    try:
        token_data = google.authorize_access_token()
        userinfo = token_data.get("userinfo") or google.userinfo()
        email = userinfo["email"].lower()
        name = userinfo.get("name", email)
        sso_id = userinfo["sub"]

        conn = get_db()
        try:
            user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            if user:
                conn.execute("UPDATE users SET last_login = ?, sso_provider = 'google', sso_id = ? WHERE id = ?",
                             (datetime.utcnow().isoformat(), sso_id, user["id"]))
                user_id = user["id"]
            else:
                user_id = str(uuid.uuid4())
                conn.execute(
                    "INSERT INTO users (id, email, name, sso_provider, sso_id) VALUES (?, ?, ?, 'google', ?)",
                    (user_id, email, name, sso_id),
                )
            conn.commit()
        finally:
            conn.close()

        jwt_token = make_token(user_id, email, name)
        return redirect(f"{frontend_url}/?token={jwt_token}")
    except Exception as e:
        return redirect(f"{frontend_url}/?error=sso_failed")


@app.route("/verify", methods=["GET"])
@require_token
def verify():
    return jsonify({"valid": True, "user": request.user})


@app.route("/me", methods=["GET"])
@require_token
def me():
    conn = get_db()
    try:
        user = conn.execute("SELECT id, email, name, sso_provider, created_at, last_login FROM users WHERE id = ?",
                            (request.user["sub"],)).fetchone()
        if not user:
            return jsonify({"error": "user not found"}), 404
        return jsonify(dict(user))
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5001, debug=os.environ.get("FLASK_DEBUG", "0") == "1")
