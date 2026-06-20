import os
import requests as http
from flask import Flask, render_template, jsonify, request, redirect, url_for

app = Flask(__name__)

AUTH_SERVICE_URL = os.environ.get("AUTH_SERVICE_URL", "http://auth-service:5001")
PRICE_SERVICE_URL = os.environ.get("PRICE_SERVICE_URL", "http://price-service:5002")
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")


@app.route("/")
def index():
    return render_template("index.html", google_client_id=GOOGLE_CLIENT_ID)


@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "frontend"})


# --- Auth proxy ---

@app.route("/api/auth/register", methods=["POST"])
def proxy_register():
    try:
        resp = http.post(f"{AUTH_SERVICE_URL}/register", json=request.get_json(), timeout=10)
        return jsonify(resp.json()), resp.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@app.route("/api/auth/login", methods=["POST"])
def proxy_login():
    try:
        resp = http.post(f"{AUTH_SERVICE_URL}/login", json=request.get_json(), timeout=10)
        return jsonify(resp.json()), resp.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@app.route("/api/auth/me")
def proxy_me():
    try:
        resp = http.get(
            f"{AUTH_SERVICE_URL}/me",
            headers={"Authorization": request.headers.get("Authorization", "")},
            timeout=10,
        )
        return jsonify(resp.json()), resp.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@app.route("/sso/google")
def sso_google():
    return redirect(f"{AUTH_SERVICE_URL}/sso/google")


# --- Price proxy ---

@app.route("/api/search")
def proxy_search():
    try:
        resp = http.get(
            f"{PRICE_SERVICE_URL}/search",
            params=request.args,
            timeout=15,
        )
        return jsonify(resp.json()), resp.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@app.route("/api/trending")
def proxy_trending():
    try:
        resp = http.get(f"{PRICE_SERVICE_URL}/trending", timeout=5)
        return jsonify(resp.json()), resp.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@app.route("/api/platforms")
def proxy_platforms():
    try:
        resp = http.get(f"{PRICE_SERVICE_URL}/platforms", timeout=5)
        return jsonify(resp.json()), resp.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@app.route("/api/watchlist", methods=["GET", "POST"])
def proxy_watchlist():
    try:
        if request.method == "GET":
            resp = http.get(f"{PRICE_SERVICE_URL}/watchlist", params=request.args, timeout=5)
        else:
            resp = http.post(f"{PRICE_SERVICE_URL}/watchlist", json=request.get_json(), timeout=5)
        return jsonify(resp.json()), resp.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@app.route("/api/watchlist/<int:item_id>", methods=["DELETE"])
def proxy_watchlist_delete(item_id: int):
    try:
        resp = http.delete(f"{PRICE_SERVICE_URL}/watchlist/{item_id}", params=request.args, timeout=5)
        return jsonify(resp.json()), resp.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 502


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=os.environ.get("FLASK_DEBUG", "0") == "1")
