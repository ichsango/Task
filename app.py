# app.py
# SmartTask AI - Full Backend (final)
# Compatible with Python 3.14 (safe shim)

# ----- SAFE SHIM for Python 3.14 -----
import pkgutil
# Avoid pkgutil.get_loader behavior that triggers find_spec(__main__) issues
pkgutil.get_loader = lambda name: None
# -------------------------------------

import os, json, base64
from datetime import datetime, timedelta
from flask import Flask, jsonify, request, render_template, send_from_directory, make_response
from flask_cors import CORS

APP_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(APP_DIR, "templates")
STATIC_DIR = os.path.join(APP_DIR, "static")
DRAW_DIR = os.path.join(STATIC_DIR, "drawings")

TASK_FILE = os.path.join(APP_DIR, "tasks.json")
PROFILE_FILE = os.path.join(APP_DIR, "profile.json")

os.makedirs(DRAW_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(TEMPLATES_DIR, exist_ok=True)

# Flask app: use a package name so Flask won't try to inspect __main__ spec
app = Flask("smarttask", template_folder=TEMPLATES_DIR, static_folder=STATIC_DIR, static_url_path="/static")
CORS(app)

# --- Utilities ---
def now_iso():
    return datetime.now().isoformat()

def load_profile():
    if not os.path.exists(PROFILE_FILE):
        p = {"name": "Siswa", "email": "", "avatar": "", "plan": "basic", "created": now_iso()}
        save_profile(p)
        return p
    try:
        with open(PROFILE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"name":"Siswa","email":"","avatar":"","plan":"basic","created":now_iso()}

def save_profile(p):
    with open(PROFILE_FILE, "w", encoding="utf-8") as f:
        json.dump(p, f, ensure_ascii=False, indent=2)

def load_tasks():
    if not os.path.exists(TASK_FILE):
        return []
    try:
        with open(TASK_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_tasks(tasks):
    with open(TASK_FILE, "w", encoding="utf-8") as f:
        json.dump(tasks, f, ensure_ascii=False, indent=2)

def format_date_iso(iso):
    if not iso:
        return ""
    try:
        d = datetime.fromisoformat(iso)
        return d.strftime("%d %B %Y")
    except Exception:
        return iso

def today_start():
    n = datetime.now()
    return n.replace(hour=0, minute=0, second=0, microsecond=0)

# --- Routes ---
@app.route("/")
def index():
    resp = make_response(render_template("index.html"))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return resp

# serve saved drawings (static route exists but explicit route okay)
@app.route("/static/drawings/<path:fn>")
def serve_drawings(fn):
    return send_from_directory(DRAW_DIR, fn)

# Profile routes
@app.route("/api/profile", methods=["GET","PATCH"])
def api_profile():
    if request.method == "GET":
        return jsonify(load_profile())
    data = request.get_json(silent=True) or {}
    p = load_profile()
    if "name" in data:
        p["name"] = data["name"]
    if "email" in data:
        p["email"] = data["email"]
    if "avatar" in data:
        p["avatar"] = data["avatar"]
    if "plan" in data:
        p["plan"] = data["plan"]
    save_profile(p)
    return jsonify({"ok": True, "profile": p})

@app.route("/api/subscribe", methods=["POST"])
def api_subscribe():
    data = request.get_json(silent=True) or {}
    plan = data.get("plan", "basic")
    if plan not in ("basic", "pro"):
        return jsonify({"ok": False, "msg": "invalid plan"}), 400
    p = load_profile()
    p["plan"] = plan
    p["subscribed_at"] = now_iso()
    save_profile(p)
    return jsonify({"ok": True, "profile": p})

# Tasks: GET POST DELETE
@app.route("/api/tasks", methods=["GET","POST","DELETE"])
def api_tasks():
    tasks = load_tasks()
    if request.method == "GET":
        return jsonify(tasks)
    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        name = (payload.get("name") or "").strip()
        deadline = payload.get("deadline","")
        priority = payload.get("priority","medium")
        note = payload.get("note","")
        if not name or not deadline:
            return jsonify({"ok": False, "msg": "name and deadline required"}), 400
        # normalize deadline to ISO if possible
        try:
            d = datetime.fromisoformat(deadline)
            iso = d.isoformat()
        except Exception:
            try:
                d = datetime.strptime(deadline, "%Y-%m-%d")
                iso = d.isoformat()
            except Exception:
                return jsonify({"ok": False, "msg": "invalid date format"}), 400
        t = {
            "id": "t" + datetime.now().strftime("%Y%m%d%H%M%S%f"),
            "name": name,
            "deadline": iso,
            "priority": priority,
            "note": note,
            "done": False
        }
        tasks.append(t)
        save_tasks(tasks)
        return jsonify({"ok": True, "task": t})
    # DELETE -> clear all
    if request.method == "DELETE":
        save_tasks([])
        return jsonify({"ok": True})

@app.route("/api/tasks/<task_id>", methods=["PATCH","DELETE"])
def api_task_modify(task_id):
    tasks = load_tasks()
    found = next((t for t in tasks if t["id"] == task_id), None)
    if not found:
        return jsonify({"ok": False, "msg": "task not found"}), 404
    if request.method == "PATCH":
        data = request.get_json(silent=True) or {}
        if "done" in data:
            found["done"] = bool(data["done"])
        if "name" in data:
            found["name"] = data["name"]
        if "deadline" in data:
            try:
                found["deadline"] = datetime.fromisoformat(data["deadline"]).isoformat()
            except Exception:
                pass
        if "priority" in data:
            found["priority"] = data["priority"]
        if "note" in data:
            found["note"] = data["note"]
        save_tasks(tasks)
        return jsonify({"ok": True, "task": found})
    if request.method == "DELETE":
        tasks = [t for t in tasks if t["id"] != task_id]
        save_tasks(tasks)
        return jsonify({"ok": True})

# Upload drawing (data_url) - Pro usage only enforced on frontend; backend will accept and save
@app.route("/api/upload_drawing", methods=["POST"])
def api_upload_drawing():
    data = request.get_json(silent=True) or {}
    data_url = data.get("data_url","")
    if not data_url.startswith("data:image"):
        return jsonify({"ok": False, "msg": "invalid data"}), 400
    try:
        header, b64 = data_url.split(",",1)
        ext = "png"
        if "jpeg" in header or "jpg" in header: ext = "jpg"
        raw = base64.b64decode(b64)
        fn = f"drawing_{datetime.now().strftime('%Y%m%d%H%M%S%f')}.{ext}"
        path = os.path.join(DRAW_DIR, fn)
        with open(path, "wb") as f:
            f.write(raw)
        url = f"/static/drawings/{fn}"
        return jsonify({"ok": True, "url": url})
    except Exception as e:
        return jsonify({"ok": False, "msg": "save failed", "err": str(e)}), 500

# Upload note (save as file) - optionally Pro
@app.route("/api/upload_note", methods=["POST"])
def api_upload_note():
    data = request.get_json(silent=True) or {}
    text = data.get("text","")
    if text is None:
        return jsonify({"ok": False, "msg": "no text"}), 400
    try:
        fn = f"note_{datetime.now().strftime('%Y%m%d%H%M%S%f')}.txt"
        path = os.path.join(STATIC_DIR, fn)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        url = f"/static/{fn}"
        return jsonify({"ok": True, "url": url})
    except Exception as e:
        return jsonify({"ok": False, "msg":"save failed","err":str(e)}), 500

# ---------------- AI / Query ----------------
@app.route("/api/query", methods=["POST"])
def api_query():
    try:
        payload = request.get_json(silent=True) or {}
        q = (payload.get("q") or "").strip()
    except Exception:
        return jsonify({"ok": False, "reply": "Request JSON tidak valid"}), 400

    if not q:
        return jsonify({"ok": False, "reply": "Pertanyaan kosong"}), 400

    try:
        profile = load_profile()
        tasks = load_tasks()
        reply = ai_process(q, tasks, profile)
        if isinstance(reply, dict) and reply.get("_save"):
            save_tasks(tasks)
            # remove _save
            reply2 = {k:v for k,v in reply.items() if k != "_save"}
            return jsonify({"ok": True, **reply2})
        return jsonify({"ok": True, "reply": reply})
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"ok": False, "reply": "Terjadi kesalahan server"}), 500

def ai_process(q, tasks, profile):
    text = q.lower().strip()

    # Small talk
    if any(w in text for w in ["halo","hai","hello","hi"]):
        return "Hai! Ada yang bisa saya bantu?"
    if "siapa kamu" in text or "kamu siapa" in text:
        return "Saya SmartTask AI — asisten tugas dan pengingat."
    if "apa kabar" in text:
        return "Baik, terima kasih! Kamu gimana?"

    # Commands
    if text.startswith("hapus"):
        name = text.replace("hapus","").strip()
        found = [t for t in tasks if name in t.get("name","").lower()]
        if len(found) == 1:
            tasks.remove(found[0])
            return {"reply": f"Tugas '{found[0]['name']}' dihapus.", "_save": True}
        if len(found) > 1:
            return f"Ditemukan {len(found)} tugas. Sebutkan nama lebih spesifik."
        return f"Tugas '{name}' tidak ditemukan."

    if text.startswith("selesai"):
        name = text.replace("selesai","").strip()
        f = next((t for t in tasks if name in t.get("name","").lower()), None)
        if f:
            f["done"] = True
            return {"reply": f"Tugas '{f['name']}' ditandai selesai.", "_save": True}
        return f"Tugas '{name}' tidak ditemukan."

    # Deadline terdekat (robust)
    if "terdekat" in text or "deadline terdekat" in text:
        upcoming = [t for t in tasks if not t.get("done")]
        def parse_dt(t):
            try:
                return datetime.fromisoformat(t.get("deadline"))
            except Exception:
                return None
        upcoming = [t for t in upcoming if parse_dt(t) is not None]
        if not upcoming:
            return "Tidak ada tugas mendatang atau semua deadline tidak valid."
        upcoming.sort(key=lambda t: parse_dt(t))
        t = upcoming[0]
        return f"Deadline terdekat adalah '{t['name']}' pada {format_date_iso(t['deadline'])}."

    if "minggu" in text:
        now = today_start(); end = now + timedelta(days=7)
        lst = []
        for t in tasks:
            try:
                d = datetime.fromisoformat(t.get("deadline"))
                if now <= d <= end and not t.get("done"):
                    lst.append(t)
            except Exception:
                pass
        if not lst:
            return "Tidak ada tugas minggu ini."
        return "Tugas minggu ini:\n" + "\n".join(f"- {x['name']} ({format_date_iso(x['deadline'])})" for x in lst)

    if "besok" in text:
        tom = today_start() + timedelta(days=1)
        lst = []
        for t in tasks:
            try:
                d = datetime.fromisoformat(t.get("deadline"))
                if d.date() == tom.date() and not t.get("done"):
                    lst.append(t)
            except Exception:
                pass
        if not lst:
            return "Tidak ada tugas untuk besok."
        return "Tugas besok:\n" + "\n".join(f"- {x['name']}" for x in lst)

    if "berapa" in text or "jumlah" in text:
        cnt = len([t for t in tasks if not t.get("done")])
        return f"Kamu punya {cnt} tugas."

    if any(k in text for k in ["tampilkan","semua","daftar"]):
        if not tasks:
            return "Belum ada tugas."
        if profile.get("plan","basic") == "pro":
            return "Daftar tugas:\n" + "\n".join(f"- {t['name']} ({format_date_iso(t['deadline'])}) • {t.get('priority','medium').upper()} • {t.get('note','')}" for t in tasks)
        return "Daftar tugas:\n" + "\n".join(f"- {t['name']} ({format_date_iso(t['deadline'])})" for t in tasks)

    # direct match by name
    for t in tasks:
        if t.get("name","").lower() in text:
            if profile.get("plan","basic") == "pro":
                return f"Deadline '{t['name']}': {format_date_iso(t['deadline'])}\nPriority: {t.get('priority','medium')}\nNote: {t.get('note','')}"
            return f"Deadline '{t['name']}': {format_date_iso(t['deadline'])}"

    # fallback
    return "Saya tidak paham. Coba: 'deadline terdekat', 'tugas minggu ini', 'tugas besok', 'berapa tugas saya', atau 'hapus <nama tugas>'."

# --- Run ---
if __name__ == "__main__":
    if not os.path.exists(TASK_FILE):
        save_tasks([])
    if not os.path.exists(PROFILE_FILE):
        save_profile({"name":"Siswa","email":"","avatar":"","plan":"basic","created":now_iso()})
    print("SmartTask AI running at http://127.0.0.1:5000/")
    app.run(debug=True, port=5000)
