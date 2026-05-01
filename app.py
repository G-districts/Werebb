from flask import Flask, render_template, request, redirect, url_for, session, jsonify, Response
import sqlite3, hashlib, json, time, os
from datetime import datetime
from functools import wraps

app = Flask(__name__)
app.secret_key = os.urandom(24).hex()

DB = "wherebazinc.db"

# ─── DB SETUP ─────────────────────────────────────────────────────────────────

def get_db():
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    return db

def init_db():
    db = get_db()
    db.executescript("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    );
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        phone TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        display_name TEXT,
        is_admin INTEGER DEFAULT 0,
        is_approved INTEGER DEFAULT 1,
        lat REAL,
        lng REAL,
        location_updated TEXT,
        push_token TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS sightings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        lat REAL NOT NULL,
        lng REAL NOT NULL,
        description TEXT,
        address TEXT,
        status TEXT DEFAULT 'pending',
        reviewed_by INTEGER,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY(user_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        admin_id INTEGER,
        title TEXT NOT NULL,
        message TEXT NOT NULL,
        alert_type TEXT DEFAULT 'general',
        target_lat REAL,
        target_lng REAL,
        radius_km REAL,
        severity TEXT DEFAULT 'medium',
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY(admin_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS alert_reads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        alert_id INTEGER,
        user_id INTEGER,
        read_at TEXT DEFAULT (datetime('now'))
    );
    """)
    # Default settings
    defaults = {
        "app_name": "Where Bazinc",
        "subject_name": "Tracked Subject",
        "subject_description": "Report any sightings immediately.",
        "subject_photo_url": "",
        "map_default_lat": "39.5501",
        "map_default_lng": "-105.7821",
        "map_default_zoom": "8",
        "alert_color": "#ff6b00",
        "allow_registration": "1",
        "require_approval": "0"
    }
    for k, v in defaults.items():
        db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
    # Default admin
    pw = hashlib.sha256("admin123".encode()).hexdigest()
    db.execute("INSERT OR IGNORE INTO users (phone, password, display_name, is_admin, is_approved) VALUES (?, ?, ?, 1, 1)",
               ("0000000000", pw, "Admin"))
    db.commit()
    db.close()

def get_setting(key, default=""):
    db = get_db()
    row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    db.close()
    return row["value"] if row else default

def get_all_settings():
    db = get_db()
    rows = db.execute("SELECT key, value FROM settings").fetchall()
    db.close()
    return {r["key"]: r["value"] for r in rows}

def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

# ─── AUTH DECORATORS ───────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
        db.close()
        if not user or not user["is_admin"]:
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)
    return decorated

# ─── SSE STREAM ───────────────────────────────────────────────────────────────

alert_stream_clients = []

def sse_event(data):
    return f"data: {json.dumps(data)}\n\n"

@app.route("/stream")
@login_required
def stream():
    user_id = session["user_id"]
    def generate():
        db = get_db()
        last_id = db.execute("SELECT MAX(id) as m FROM alerts").fetchone()["m"] or 0
        db.close()
        while True:
            time.sleep(4)
            try:
                db = get_db()
                new_alerts = db.execute(
                    "SELECT * FROM alerts WHERE id > ? ORDER BY id ASC", (last_id,)
                ).fetchall()
                db.close()
                for a in new_alerts:
                    last_id = a["id"]
                    yield sse_event({
                        "type": "alert",
                        "id": a["id"],
                        "title": a["title"],
                        "message": a["message"],
                        "severity": a["severity"],
                        "alert_type": a["alert_type"]
                    })
            except:
                break
    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

# ─── ROUTES ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    s = get_all_settings()
    return render_template("index.html", s=s)

@app.route("/register", methods=["GET","POST"])
def register():
    s = get_all_settings()
    if s.get("allow_registration","1") != "1":
        return render_template("register.html", s=s, error="Registration is currently closed.")
    if request.method == "POST":
        phone = request.form.get("phone","").strip().replace("-","").replace(" ","").replace("(","").replace(")","")
        pw = request.form.get("password","")
        name = request.form.get("display_name","").strip()
        if len(phone) < 10:
            return render_template("register.html", s=s, error="Enter a valid 10-digit phone number.")
        if len(pw) < 6:
            return render_template("register.html", s=s, error="Password must be at least 6 characters.")
        db = get_db()
        existing = db.execute("SELECT id FROM users WHERE phone=?", (phone,)).fetchone()
        if existing:
            db.close()
            return render_template("register.html", s=s, error="That phone number is already registered.")
        approved = 0 if s.get("require_approval","0") == "1" else 1
        db.execute("INSERT INTO users (phone, password, display_name, is_approved) VALUES (?,?,?,?)",
                   (phone, hash_pw(pw), name or phone, approved))
        db.commit()
        db.close()
        if approved:
            return redirect(url_for("login", msg="Account created! Sign in below."))
        return redirect(url_for("login", msg="Account created! Awaiting admin approval."))
    return render_template("register.html", s=s)

@app.route("/login", methods=["GET","POST"])
def login():
    s = get_all_settings()
    msg = request.args.get("msg","")
    if request.method == "POST":
        phone = request.form.get("phone","").strip().replace("-","").replace(" ","").replace("(","").replace(")","")
        pw = request.form.get("password","")
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE phone=? AND password=?", (phone, hash_pw(pw))).fetchone()
        db.close()
        if not user:
            return render_template("login.html", s=s, error="Invalid phone number or password.")
        if not user["is_approved"]:
            return render_template("login.html", s=s, error="Your account is pending admin approval.")
        session["user_id"] = user["id"]
        session["is_admin"] = bool(user["is_admin"])
        session["phone"] = user["phone"]
        return redirect(url_for("admin_dashboard") if user["is_admin"] else url_for("dashboard"))
    return render_template("login.html", s=s, error="", msg=msg)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

@app.route("/dashboard")
@login_required
def dashboard():
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
    sightings = db.execute(
        "SELECT s.*, u.phone, u.display_name FROM sightings s JOIN users u ON s.user_id=u.id ORDER BY s.created_at DESC LIMIT 20"
    ).fetchall()
    alerts = db.execute("SELECT * FROM alerts ORDER BY created_at DESC LIMIT 10").fetchall()
    db.close()
    s = get_all_settings()
    return render_template("dashboard.html", s=s, user=user, sightings=sightings, alerts=alerts)

@app.route("/report", methods=["GET","POST"])
@login_required
def report():
    s = get_all_settings()
    if request.method == "POST":
        lat = request.form.get("lat")
        lng = request.form.get("lng")
        desc = request.form.get("description","").strip()
        address = request.form.get("address","").strip()
        if not lat or not lng:
            return render_template("report.html", s=s, error="Location is required.")
        db = get_db()
        db.execute("INSERT INTO sightings (user_id, lat, lng, description, address) VALUES (?,?,?,?,?)",
                   (session["user_id"], float(lat), float(lng), desc, address))
        db.commit()
        db.close()
        return redirect(url_for("dashboard"))
    return render_template("report.html", s=s)

@app.route("/my-location", methods=["POST"])
@login_required
def update_location():
    data = request.json
    lat = data.get("lat")
    lng = data.get("lng")
    if lat is None or lng is None:
        return jsonify({"ok": False})
    db = get_db()
    db.execute("UPDATE users SET lat=?, lng=?, location_updated=datetime('now') WHERE id=?",
               (lat, lng, session["user_id"]))
    db.commit()
    db.close()
    return jsonify({"ok": True})

# ─── ADMIN ROUTES ─────────────────────────────────────────────────────────────

@app.route("/admin")
@admin_required
def admin_dashboard():
    db = get_db()
    users = db.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
    sightings = db.execute(
        "SELECT s.*, u.phone, u.display_name FROM sightings s JOIN users u ON s.user_id=u.id ORDER BY s.created_at DESC"
    ).fetchall()
    alerts = db.execute("SELECT a.*, u.display_name FROM alerts a JOIN users u ON a.admin_id=u.id ORDER BY a.created_at DESC").fetchall()
    db.close()
    s = get_all_settings()
    return render_template("admin.html", s=s, users=users, sightings=sightings, alerts=alerts)

@app.route("/admin/settings", methods=["POST"])
@admin_required
def admin_settings():
    db = get_db()
    fields = ["app_name","subject_name","subject_description","subject_photo_url",
              "map_default_lat","map_default_lng","map_default_zoom",
              "alert_color","allow_registration","require_approval"]
    for f in fields:
        val = request.form.get(f, "")
        db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)", (f, val))
    db.commit()
    db.close()
    return redirect(url_for("admin_dashboard") + "#settings")

@app.route("/admin/alert", methods=["POST"])
@admin_required
def send_alert():
    title = request.form.get("title","").strip()
    message = request.form.get("message","").strip()
    alert_type = request.form.get("alert_type","general")
    severity = request.form.get("severity","medium")
    target_lat = request.form.get("target_lat") or None
    target_lng = request.form.get("target_lng") or None
    radius_km = request.form.get("radius_km") or None
    if not title or not message:
        return redirect(url_for("admin_dashboard"))
    db = get_db()
    db.execute("INSERT INTO alerts (admin_id, title, message, alert_type, severity, target_lat, target_lng, radius_km) VALUES (?,?,?,?,?,?,?,?)",
               (session["user_id"], title, message, alert_type, severity,
                float(target_lat) if target_lat else None,
                float(target_lng) if target_lng else None,
                float(radius_km) if radius_km else None))
    db.commit()
    db.close()
    return redirect(url_for("admin_dashboard") + "#alerts")

@app.route("/admin/sighting/<int:sid>", methods=["POST"])
@admin_required
def review_sighting(sid):
    status = request.form.get("status","reviewed")
    db = get_db()
    db.execute("UPDATE sightings SET status=?, reviewed_by=? WHERE id=?",
               (status, session["user_id"], sid))
    db.commit()
    db.close()
    return redirect(url_for("admin_dashboard") + "#sightings")

@app.route("/admin/user/<int:uid>", methods=["POST"])
@admin_required
def manage_user(uid):
    action = request.form.get("action")
    db = get_db()
    if action == "approve":
        db.execute("UPDATE users SET is_approved=1 WHERE id=?", (uid,))
    elif action == "revoke":
        db.execute("UPDATE users SET is_approved=0 WHERE id=?", (uid,))
    elif action == "make_admin":
        db.execute("UPDATE users SET is_admin=1 WHERE id=?", (uid,))
    elif action == "remove_admin":
        db.execute("UPDATE users SET is_admin=0 WHERE id=?", (uid,))
    elif action == "delete":
        db.execute("DELETE FROM users WHERE id=? AND id != ?", (uid, session["user_id"]))
    db.commit()
    db.close()
    return redirect(url_for("admin_dashboard") + "#users")

# ─── API ──────────────────────────────────────────────────────────────────────

@app.route("/api/sightings")
@login_required
def api_sightings():
    db = get_db()
    rows = db.execute(
        "SELECT s.id, s.lat, s.lng, s.description, s.address, s.status, s.created_at, u.display_name "
        "FROM sightings s JOIN users u ON s.user_id=u.id ORDER BY s.created_at DESC LIMIT 50"
    ).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/users/locations")
@admin_required
def api_user_locations():
    db = get_db()
    rows = db.execute(
        "SELECT id, phone, display_name, lat, lng, location_updated FROM users WHERE lat IS NOT NULL"
    ).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/alerts/latest")
@login_required
def api_alerts_latest():
    after = request.args.get("after", 0)
    db = get_db()
    rows = db.execute("SELECT * FROM alerts WHERE id > ? ORDER BY id DESC LIMIT 5", (after,)).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/stats")
@admin_required
def api_stats():
    db = get_db()
    total_users = db.execute("SELECT COUNT(*) as c FROM users WHERE is_admin=0").fetchone()["c"]
    total_sightings = db.execute("SELECT COUNT(*) as c FROM sightings").fetchone()["c"]
    pending = db.execute("SELECT COUNT(*) as c FROM sightings WHERE status='pending'").fetchone()["c"]
    total_alerts = db.execute("SELECT COUNT(*) as c FROM alerts").fetchone()["c"]
    db.close()
    return jsonify({"users": total_users, "sightings": total_sightings, "pending": pending, "alerts": total_alerts})

# ─── PWA ──────────────────────────────────────────────────────────────────────

@app.route("/manifest.json")
def manifest():
    name = get_setting("app_name", "Where Bazinc")
    return jsonify({
        "name": name,
        "short_name": name,
        "start_url": "/",
        "display": "standalone",
        "background_color": "#0a0e17",
        "theme_color": "#ff6b00",
        "description": "Community tracking and alert system",
        "icons": [
            {"src": "/static/icons/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/static/icons/icon-512.png", "sizes": "512x512", "type": "image/png"}
        ]
    })

@app.route("/sw.js")
def service_worker():
    return app.send_static_file("sw.js")

if __name__ == "__main__":
    init_db()
    app.run(debug=True, host="0.0.0.0", port=5000, threaded=True)
