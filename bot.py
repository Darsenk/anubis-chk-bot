import os
import sys
import time
import json
import requests
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler

_BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _BASE)

from firebase_manager import (
    registrar_usuario,
    verificar_login,
    obtener_todos_usuarios,
    TELEGRAM_TOKEN,
    ADMIN_CHAT_ID,
    get_db
)

API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

_estados = {}
_pendientes = {}

# ══════════════════════════════════════════════════════════════
# HTTP SERVER
# ══════════════════════════════════════════════════════════════
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({
            "status": "ok",
            "uptime": int(time.time())
        }).encode())

    def log_message(self, *args):
        pass


def run_http_server():
    port = int(os.environ.get("PORT", 8000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    print(f"🌐 HTTP en puerto {port}")
    server.serve_forever()


# ══════════════════════════════════════════════════════════════
# TELEGRAM
# ══════════════════════════════════════════════════════════════
def send(chat_id, text):
    try:
        requests.post(f"{API}/sendMessage", data={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML"
        }, timeout=10)
    except Exception as e:
        print("❌ SEND:", e)


def get_updates(offset=0):
    try:
        r = requests.get(f"{API}/getUpdates",
                         params={"offset": offset, "timeout": 30},
                         timeout=35)
        return r.json().get("result", [])
    except Exception as e:
        print("❌ UPDATES:", e)
        return []


# ══════════════════════════════════════════════════════════════
# HANDLER
# ══════════════════════════════════════════════════════════════
def handle(msg):
    chat_id = str(msg["chat"]["id"])
    text = msg.get("text", "").strip()
    username = msg.get("from", {}).get("username", "")
    nombre = msg.get("from", {}).get("first_name", "Usuario")

    es_admin = chat_id == str(ADMIN_CHAT_ID)

    # ── START ──
    if text == "/start":
        send(chat_id,
             f"𓂀 <b>ANUBIS CHK</b>\n\n"
             f"Hola {nombre}\n\n"
             f"/registro\n/mislives\n"
             + ("\n/admin" if es_admin else ""))
        return

    # ── PANEL ADMIN ──
    if text == "/admin" and es_admin:
        send(chat_id,
             "👑 <b>PANEL ADMIN PRO</b>\n\n"
             "/usuarios\n"
             "/buscar username\n"
             "/adduser user pass chatid\n"
             "/deluser username\n"
             "/top\n"
             "/reset username\n"
             "/ban username\n"
             "/unban username")
        return

    # ── USUARIOS ──
    if text == "/usuarios" and es_admin:
        users = obtener_todos_usuarios()
        txt = "👥 USERS\n\n"
        for u in users:
            txt += f"{u['username']} | {u.get('lives_count',0)}\n"
        send(chat_id, txt)
        return

    # ── BUSCAR ──
    if text.startswith("/buscar") and es_admin:
        try:
            _, user = text.split()
            db = get_db()
            doc = db.collection("usuarios").document(user.lower()).get()

            if not doc.exists:
                send(chat_id, "❌ No existe")
                return

            u = doc.to_dict()
            send(chat_id,
                 f"👤 {u['username']}\n"
                 f"📊 Lives: {u.get('lives_count',0)}\n"
                 f"🆔 {u.get('chat_id')}\n"
                 f"🚫 Activo: {u.get('activo', True)}")
        except:
            send(chat_id, "Uso: /buscar username")
        return

    # ── DELETE ──
    if text.startswith("/deluser") and es_admin:
        try:
            _, user = text.split()
            db = get_db()
            db.collection("usuarios").document(user.lower()).delete()
            send(chat_id, f"🗑️ {user} eliminado")
        except:
            send(chat_id, "Uso: /deluser username")
        return

    # ── TOP ──
    if text == "/top" and es_admin:
        users = obtener_todos_usuarios()
        users = sorted(users, key=lambda x: x.get("lives_count", 0), reverse=True)

        txt = "🏆 TOP\n\n"
        for i, u in enumerate(users[:10], 1):
            txt += f"{i}. {u['username']} → {u.get('lives_count',0)}\n"

        send(chat_id, txt)
        return

    # ── RESET ──
    if text.startswith("/reset") and es_admin:
        try:
            _, user = text.split()
            db = get_db()
            db.collection("usuarios").document(user.lower()).update({
                "lives_count": 0
            })
            send(chat_id, f"🔄 {user} reseteado")
        except:
            send(chat_id, "Uso: /reset username")
        return

    # ── BAN ──
    if text.startswith("/ban") and es_admin:
        try:
            _, user = text.split()
            db = get_db()
            db.collection("usuarios").document(user.lower()).update({
                "activo": False
            })
            send(chat_id, f"🚫 {user} baneado")
        except:
            send(chat_id, "Uso: /ban username")
        return

    # ── UNBAN ──
    if text.startswith("/unban") and es_admin:
        try:
            _, user = text.split()
            db = get_db()
            db.collection("usuarios").document(user.lower()).update({
                "activo": True
            })
            send(chat_id, f"✅ {user} activado")
        except:
            send(chat_id, "Uso: /unban username")
        return

    # ── REGISTRO ──
    if text == "/registro":
        _estados[chat_id] = {"step": "user"}
        send(chat_id, "👤 Usuario:")
        return

    estado = _estados.get(chat_id)

    if estado:
        if estado["step"] == "user":
            _estados[chat_id] = {"step": "pass", "user": text}
            send(chat_id, "🔑 Password:")
            return

        if estado["step"] == "pass":
            _estados[chat_id] = {
                "step": "confirm",
                "user": estado["user"],
                "pass": text
            }
            send(chat_id, f"Confirmar:\n{estado['user']}\n{text}\n\nSI/NO")
            return

        if estado["step"] == "confirm":
            if text.upper() == "SI":
                uname = estado["user"]
                pwd = estado["pass"]

                db = get_db()
                if db.collection("usuarios").document(uname.lower()).get().exists:
                    send(chat_id, "❌ Usuario existe")
                    del _estados[chat_id]
                    return

                _pendientes[chat_id] = {
                    "username": uname,
                    "password": pwd,
                    "chat_id": chat_id,
                    "telegram_user": username
                }

                send(chat_id, "⏳ Esperando aprobación")

                send(ADMIN_CHAT_ID,
                     f"🔔 Nuevo registro\n\n"
                     f"{uname}\n\n"
                     f"/adduser {uname} {pwd} {chat_id}")

                del _estados[chat_id]
                return
            else:
                send(chat_id, "❌ Cancelado")
                del _estados[chat_id]
                return

    # ── ADDUSER ──
    if text.startswith("/adduser") and es_admin:
        try:
            _, u, p, cid = text.split()
            res = registrar_usuario(u, p, cid)

            if res["ok"]:
                send(chat_id, f"✅ {u} creado")
                send(cid, "🎉 Acceso aprobado")
            else:
                send(chat_id, f"❌ {res['error']}")
        except:
            send(chat_id, "Uso: /adduser user pass chatid")
        return

    # ── MIS LIVES ──
    if text == "/mislives":
        users = obtener_todos_usuarios()
        for u in users:
            if str(u.get("chat_id")) == chat_id:
                send(chat_id, f"📊 Lives: {u.get('lives_count',0)}")
                return
        send(chat_id, "❌ No registrado")


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════
start_time = time.time()

def main():
    Thread(target=run_http_server, daemon=True).start()

    send(ADMIN_CHAT_ID, "🚀 BOT ONLINE")

    offset = 0

    while True:
        updates = get_updates(offset)

        for u in updates:
            offset = u["update_id"] + 1
            if "message" in u:
                try:
                    handle(u["message"])
                except Exception as e:
                    print("❌ HANDLE:", e)

        time.sleep(1)


# ══════════════════════════════════════════════════════════════
# AUTO RESTART
# ══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    while True:
        try:
            main()
        except Exception as e:
            print("💀 CRASH:", e)
            time.sleep(5)
