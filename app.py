from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import sqlite3, hashlib, os
from functools import wraps

app = Flask(__name__)
app.secret_key = os.urandom(24).hex()
DB = "wherebazinc.db"

# ── DB ─────────────────────────────────────────────────────────────────
def get_db():
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    return db

def init_db():
    db = get_db()
    db.executescript("""
    CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        phone TEXT UNIQUE NOT NULL, password TEXT NOT NULL,
        display_name TEXT, is_admin INTEGER DEFAULT 0,
        is_approved INTEGER DEFAULT 1,
        lat REAL, lng REAL, location_updated TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS sightings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, lat REAL NOT NULL, lng REAL NOT NULL,
        description TEXT, address TEXT,
        status TEXT DEFAULT 'pending', reviewed_by INTEGER,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY(user_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        admin_id INTEGER, title TEXT NOT NULL, message TEXT NOT NULL,
        alert_type TEXT DEFAULT 'general',
        target_lat REAL, target_lng REAL, radius_km REAL,
        severity TEXT DEFAULT 'medium',
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY(admin_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS alert_acks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        alert_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
        acked_at TEXT DEFAULT (datetime('now')),
        UNIQUE(alert_id, user_id)
    );
    """)
    defaults = {
        "app_name": "Where Bazinc", "teacher_name": "Mr. Smith",
        "teacher_description": "Spot the teacher? Drop a pin and alert everyone!",
        "teacher_photo_url": "",
        "map_default_lat": "39.5501", "map_default_lng": "-105.7821",
        "map_default_zoom": "15", "allow_registration": "1", "require_approval": "0"
    }
    for k, v in defaults.items():
        db.execute("INSERT OR IGNORE INTO settings (key,value) VALUES (?,?)", (k, v))
    pw = hashlib.sha256("admin123".encode()).hexdigest()
    db.execute("INSERT OR IGNORE INTO users (phone,password,display_name,is_admin,is_approved) VALUES (?,?,?,1,1)",
               ("0000000000", pw, "Admin"))
    db.commit(); db.close()

def get_all_settings():
    db = get_db()
    rows = db.execute("SELECT key,value FROM settings").fetchall()
    db.close()
    return {r["key"]: r["value"] for r in rows}

def get_setting(key, default=""):
    db = get_db()
    r = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    db.close()
    return r["value"] if r else default

def hash_pw(pw): return hashlib.sha256(pw.encode()).hexdigest()

# ── AUTH ───────────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def dec(*a, **kw):
        if "user_id" not in session: return redirect(url_for("login"))
        return f(*a, **kw)
    return dec

def admin_required(f):
    @wraps(f)
    def dec(*a, **kw):
        if "user_id" not in session: return redirect(url_for("login"))
        db = get_db()
        u = db.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
        db.close()
        if not u or not u["is_admin"]: return redirect(url_for("dashboard"))
        return f(*a, **kw)
    return dec

# ── PAGES ──────────────────────────────────────────────────────────────
@app.route("/")
def index():
    if "user_id" in session: return redirect(url_for("dashboard"))
    return render_template("index.html", s=get_all_settings())

@app.route("/register", methods=["GET","POST"])
def register():
    s = get_all_settings()
    if s.get("allow_registration","1") != "1":
        return render_template("register.html", s=s, error="Registration is currently closed.")
    if request.method == "POST":
        phone = request.form.get("phone","").strip().replace("-","").replace("(","").replace(")","").replace(" ","")
        pw    = request.form.get("password","")
        name  = request.form.get("display_name","").strip()
        if len(phone) < 10:
            return render_template("register.html", s=s, error="Enter a valid 10-digit phone number.")
        if len(pw) < 6:
            return render_template("register.html", s=s, error="Password must be at least 6 characters.")
        db = get_db()
        if db.execute("SELECT id FROM users WHERE phone=?", (phone,)).fetchone():
            db.close()
            return render_template("register.html", s=s, error="That phone number is already registered.")
        approved = 0 if s.get("require_approval","0") == "1" else 1
        db.execute("INSERT INTO users (phone,password,display_name,is_approved) VALUES (?,?,?,?)",
                   (phone, hash_pw(pw), name or phone, approved))
        db.commit(); db.close()
        msg = "Account created! Sign in." if approved else "Account created! Awaiting admin approval."
        return redirect(url_for("login", msg=msg))
    return render_template("register.html", s=s)

@app.route("/login", methods=["GET","POST"])
def login():
    s   = get_all_settings()
    msg = request.args.get("msg","")
    if request.method == "POST":
        phone = request.form.get("phone","").strip().replace("-","").replace("(","").replace(")","").replace(" ","")
        pw    = request.form.get("password","")
        db    = get_db()
        u     = db.execute("SELECT * FROM users WHERE phone=? AND password=?", (phone, hash_pw(pw))).fetchone()
        db.close()
        if not u: return render_template("login.html", s=s, error="Wrong phone or password.", msg="")
        if not u["is_approved"]: return render_template("login.html", s=s, error="Account pending approval.", msg="")
        session.update({"user_id": u["id"], "is_admin": bool(u["is_admin"]),
                        "phone": u["phone"], "disp_name": u["display_name"] or u["phone"]})
        return redirect(url_for("admin_dashboard") if u["is_admin"] else url_for("dashboard"))
    return render_template("login.html", s=s, error="", msg=msg)

@app.route("/logout")
def logout():
    session.clear(); return redirect(url_for("index"))

@app.route("/dashboard")
@login_required
def dashboard():
    db = get_db()
    user      = db.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
    sightings = db.execute("SELECT s.*,u.phone,u.display_name FROM sightings s JOIN users u ON s.user_id=u.id ORDER BY s.created_at DESC LIMIT 30").fetchall()
    alerts    = db.execute("SELECT * FROM alerts ORDER BY created_at DESC LIMIT 20").fetchall()
    db.close()
    return render_template("dashboard.html", s=get_all_settings(), user=user, sightings=sightings, alerts=alerts)

@app.route("/report", methods=["GET","POST"])
@login_required
def report():
    s = get_all_settings()
    if request.method == "POST":
        lat  = request.form.get("lat")
        lng  = request.form.get("lng")
        desc = request.form.get("description","").strip()
        addr = request.form.get("address","").strip()
        if not lat or not lng:
            return render_template("report.html", s=s, error="Location is required.")
        db = get_db()
        db.execute("INSERT INTO sightings (user_id,lat,lng,description,address) VALUES (?,?,?,?,?)",
                   (session["user_id"], float(lat), float(lng), desc, addr))
        # Auto-alert admins about new sighting
        reporter = session.get("disp_name", session.get("phone","Someone"))
        loc_str  = addr or f'{float(lat):.4f}, {float(lng):.4f}'
        db.execute("INSERT INTO alerts (admin_id,title,message,alert_type,severity,target_lat,target_lng) VALUES (?,?,?,?,?,?,?)",
                   (session["user_id"],
                    f"📍 {s.get('teacher_name','Teacher')} Spotted!",
                    f"{reporter} saw them at {loc_str}. {desc}".strip().rstrip(".") + ".",
                    "sighting", "high", float(lat), float(lng)))
        db.commit(); db.close()
        return redirect(url_for("dashboard"))
    return render_template("report.html", s=s)

@app.route("/my-location", methods=["POST"])
@login_required
def update_location():
    d = request.json
    lat, lng = d.get("lat"), d.get("lng")
    if lat is None: return jsonify({"ok": False})
    db = get_db()
    db.execute("UPDATE users SET lat=?,lng=?,location_updated=datetime('now') WHERE id=?",
               (lat, lng, session["user_id"]))
    db.commit(); db.close()
    return jsonify({"ok": True})

@app.route("/profile", methods=["POST"])
@login_required
def update_profile():
    name = request.form.get("display_name","").strip()
    if name:
        db = get_db()
        db.execute("UPDATE users SET display_name=? WHERE id=?", (name, session["user_id"]))
        db.commit(); db.close()
        session["disp_name"] = name
    return redirect(request.referrer or url_for("dashboard"))

# ── ADMIN ──────────────────────────────────────────────────────────────
@app.route("/admin")
@admin_required
def admin_dashboard():
    db = get_db()
    users     = db.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
    sightings = db.execute("SELECT s.*,u.phone,u.display_name FROM sightings s JOIN users u ON s.user_id=u.id ORDER BY s.created_at DESC").fetchall()
    alerts    = db.execute("SELECT a.*,u.display_name as sent_by FROM alerts a JOIN users u ON a.admin_id=u.id ORDER BY a.created_at DESC").fetchall()
    db.close()
    return render_template("admin.html", s=get_all_settings(), users=users, sightings=sightings, alerts=alerts)

@app.route("/admin/settings", methods=["POST"])
@admin_required
def admin_settings():
    db = get_db()
    for f in ["app_name","teacher_name","teacher_description","teacher_photo_url",
              "map_default_lat","map_default_lng","map_default_zoom",
              "allow_registration","require_approval"]:
        db.execute("INSERT OR REPLACE INTO settings (key,value) VALUES (?,?)", (f, request.form.get(f,"")))
    db.commit(); db.close()
    return redirect(url_for("admin_dashboard") + "#settings")

@app.route("/admin/set-map-location", methods=["POST"])
@admin_required
def admin_set_map_location():
    d = request.json
    lat, lng, zoom = d.get("lat"), d.get("lng"), d.get("zoom", 15)
    if lat is None: return jsonify({"ok": False})
    db = get_db()
    for k, v in [("map_default_lat", str(lat)), ("map_default_lng", str(lng)), ("map_default_zoom", str(int(zoom)))]:
        db.execute("INSERT OR REPLACE INTO settings (key,value) VALUES (?,?)", (k, v))
    db.commit(); db.close()
    return jsonify({"ok": True})

@app.route("/admin/alert", methods=["POST"])
@admin_required
def send_alert():
    title   = request.form.get("title","").strip()
    message = request.form.get("message","").strip()
    if not title or not message: return redirect(url_for("admin_dashboard"))
    db = get_db()
    db.execute("INSERT INTO alerts (admin_id,title,message,alert_type,severity,target_lat,target_lng,radius_km) VALUES (?,?,?,?,?,?,?,?)",
               (session["user_id"], title, message,
                request.form.get("alert_type","general"),
                request.form.get("severity","medium"),
                float(request.form["target_lat"]) if request.form.get("target_lat") else None,
                float(request.form["target_lng"]) if request.form.get("target_lng") else None,
                float(request.form["radius_km"])  if request.form.get("radius_km")  else None))
    db.commit(); db.close()
    return redirect(url_for("admin_dashboard") + "#alerts")

@app.route("/admin/alert/<int:aid>/delete", methods=["POST"])
@admin_required
def delete_alert(aid):
    db = get_db()
    db.execute("DELETE FROM alert_acks WHERE alert_id=?", (aid,))
    db.execute("DELETE FROM alerts WHERE id=?", (aid,))
    db.commit(); db.close()
    return redirect(url_for("admin_dashboard") + "#alerts")

@app.route("/admin/sighting/<int:sid>", methods=["POST"])
@admin_required
def review_sighting(sid):
    db = get_db()
    db.execute("UPDATE sightings SET status=?,reviewed_by=? WHERE id=?",
               (request.form.get("status","reviewed"), session["user_id"], sid))
    db.commit(); db.close()
    return redirect(url_for("admin_dashboard") + "#sightings")

@app.route("/admin/sighting/<int:sid>/delete", methods=["POST"])
@admin_required
def delete_sighting(sid):
    db = get_db()
    db.execute("DELETE FROM sightings WHERE id=?", (sid,))
    db.commit(); db.close()
    return redirect(url_for("admin_dashboard") + "#sightings")

@app.route("/admin/user/<int:uid>", methods=["POST"])
@admin_required
def manage_user(uid):
    action = request.form.get("action")
    db = get_db()
    if   action == "approve":      db.execute("UPDATE users SET is_approved=1 WHERE id=?", (uid,))
    elif action == "revoke":       db.execute("UPDATE users SET is_approved=0 WHERE id=?", (uid,))
    elif action == "make_admin":   db.execute("UPDATE users SET is_admin=1 WHERE id=?",    (uid,))
    elif action == "remove_admin": db.execute("UPDATE users SET is_admin=0 WHERE id=?",    (uid,))
    elif action == "delete" and uid != session["user_id"]:
        db.execute("DELETE FROM users WHERE id=?", (uid,))
    db.commit(); db.close()
    return redirect(url_for("admin_dashboard") + "#users")

# ── API ────────────────────────────────────────────────────────────────
@app.route("/api/sightings")
@login_required
def api_sightings():
    db   = get_db()
    rows = db.execute(
        "SELECT s.id,s.lat,s.lng,s.description,s.address,s.status,s.created_at,u.display_name "
        "FROM sightings s JOIN users u ON s.user_id=u.id ORDER BY s.created_at DESC LIMIT 60"
    ).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/users/locations")
@login_required
def api_user_locations():
    db   = get_db()
    rows = db.execute(
        "SELECT id,phone,display_name,lat,lng,location_updated,is_admin FROM users WHERE lat IS NOT NULL"
    ).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/alerts/latest")
@login_required
def api_alerts_latest():
    after = request.args.get("after", 0, type=int)
    uid   = session["user_id"]
    db    = get_db()
    rows  = db.execute(
        "SELECT a.* FROM alerts a "
        "WHERE a.id > ? AND a.id NOT IN (SELECT alert_id FROM alert_acks WHERE user_id=?) "
        "ORDER BY a.id ASC LIMIT 10", (after, uid)
    ).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/alerts/ack", methods=["POST"])
@login_required
def ack_alert():
    aid = request.json.get("alert_id")
    if not aid: return jsonify({"ok": False})
    db = get_db()
    db.execute("INSERT OR IGNORE INTO alert_acks (alert_id,user_id) VALUES (?,?)", (aid, session["user_id"]))
    db.commit(); db.close()
    return jsonify({"ok": True})

@app.route("/api/stats")
@admin_required
def api_stats():
    db = get_db()
    r  = {
        "users":     db.execute("SELECT COUNT(*) FROM users WHERE is_admin=0").fetchone()[0],
        "sightings": db.execute("SELECT COUNT(*) FROM sightings").fetchone()[0],
        "pending":   db.execute("SELECT COUNT(*) FROM sightings WHERE status='pending'").fetchone()[0],
        "alerts":    db.execute("SELECT COUNT(*) FROM alerts").fetchone()[0],
    }
    db.close()
    return jsonify(r)

# ── PWA ────────────────────────────────────────────────────────────────
@app.route("/manifest.json")
def manifest():
    name = get_setting("app_name","Where Bazinc")
    return jsonify({
        "name": name, "short_name": name, "start_url": "/",
        "display": "standalone",
        "background_color": "#f8f9fc", "theme_color": "#6366f1",
        "icons": [
            {"src":"/static/icons/icon-192.png","sizes":"192x192","type":"image/png"},
            {"src":"/static/icons/icon-512.png","sizes":"512x512","type":"image/png"}
        ]
    })

@app.route("/sw.js")
def service_worker():
    return app.send_static_file("sw.js")

if __name__ == "__main__":
    init_db()
    print("Where Bazinc → http://localhost:5000")
    print("Admin: 0000000000 / admin123")
    app.run(debug=False, host="0.0.0.0", port=5000, threaded=True)
