"""
═══════════════════════════════════════════════════════════════
ANUBIS CHK BOT — WEBHOOK VERSION (KOYEB OPTIMIZED)
═══════════════════════════════════════════════════════════════
Bot de Telegram con webhooks + Flask
Optimizado para Koyeb - NO SE DUERME
═══════════════════════════════════════════════════════════════
"""
import os
import sys
import time
import json
import requests
import traceback
from threading import Lock
from datetime import datetime
from collections import deque
from flask import Flask, request, jsonify

_BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _BASE)

from firebase_manager import (
    registrar_usuario,
    verificar_login,
    obtener_todos_usuarios,
    stats_globales,
    bloquear_usuario,
    desbloquear_usuario,
    eliminar_usuario,
    cambiar_password,
    obtener_logs_recientes,
    get_system_info,
    TELEGRAM_TOKEN,
    ADMIN_CHAT_ID,
    CREATOR_USERNAME,
)

API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# ══════════════════════════════════════════════════════════════
# SISTEMA DE SOLICITUDES
# ══════════════════════════════════════════════════════════════

pending_requests = {}  # {chat_id: {"username": "xxx", "password": "xxx", "timestamp": xxx}}
request_lock = Lock()

def add_request(chat_id, username, password):
    """Agregar solicitud de acceso"""
    with request_lock:
        pending_requests[chat_id] = {
            "username": username,
            "password": password,
            "timestamp": time.time(),
        }

def get_request(chat_id):
    """Obtener solicitud por chat_id"""
    with request_lock:
        return pending_requests.get(chat_id)

def remove_request(chat_id):
    """Eliminar solicitud"""
    with request_lock:
        if chat_id in pending_requests:
            del pending_requests[chat_id]

def get_all_requests():
    """Obtener todas las solicitudes pendientes"""
    with request_lock:
        return dict(pending_requests)

# ══════════════════════════════════════════════════════════════
# SISTEMA DE SALUD
# ══════════════════════════════════════════════════════════════

class HealthMonitor:
    def __init__(self):
        self.start_time = time.time()
        self.last_update = time.time()
        self.errors = deque(maxlen=100)
        self.error_lock = Lock()
        self.request_count = 0
        self.webhook_count = 0
        
    def record_error(self, error_type, details):
        with self.error_lock:
            self.errors.append({
                "type": error_type,
                "details": str(details),
                "timestamp": time.time()
            })
            
    def get_recent_errors(self, window=300):
        now = time.time()
        with self.error_lock:
            return [e for e in self.errors if now - e["timestamp"] < window]
    
    def update_activity(self):
        self.last_update = time.time()
        self.webhook_count += 1
        
    def get_stats(self):
        uptime = int(time.time() - self.start_time)
        return {
            "status": "healthy",
            "uptime": uptime,
            "uptime_formatted": f"{uptime//3600}h {(uptime%3600)//60}m {uptime%60}s",
            "requests": self.request_count,
            "webhooks_received": self.webhook_count,
            "errors_5min": len(self.get_recent_errors(300)),
            "errors_15min": len(self.get_recent_errors(900)),
            "last_activity": int(time.time() - self.last_update),
        }

health = HealthMonitor()

# ══════════════════════════════════════════════════════════════
# TELEGRAM API
# ══════════════════════════════════════════════════════════════

def send(chat_id, text, reply_markup=None, parse_mode="HTML"):
    """Envía mensaje de Telegram"""
    try:
        health.request_count += 1
        
        data = {
            "chat_id": chat_id,
            "text": text[:4096],
            "parse_mode": parse_mode
        }
        
        if reply_markup:
            data["reply_markup"] = json.dumps(reply_markup)
        
        r = requests.post(
            f"{API}/sendMessage",
            json=data,
            timeout=15
        )
        
        return r.status_code == 200
        
    except Exception as e:
        print(f"⚠️ Error send: {e}")
        health.record_error("send", e)
        return False

# ══════════════════════════════════════════════════════════════
# HANDLERS
# ══════════════════════════════════════════════════════════════

def handle(msg):
    """Procesa mensajes"""
    try:
        chat_id = str(msg["chat"]["id"])
        text = msg.get("text", "").strip()
        telegram_user = msg.get("from", {}).get("username", "desconocido")
        
        if not text:
            return

        # ── ADMIN CHECK ──
        is_admin = chat_id == ADMIN_CHAT_ID

        # ── START ──
        if text == "/start":
            send(chat_id,
                 f"👋 Bienvenido a <b>ANUBIS CHK</b>\n\n"
                 f"🔐 Para solicitar acceso usa:\n"
                 f"<code>/register [usuario] [contraseña]</code>\n\n"
                 f"Si ya tienes cuenta usa:\n"
                 f"<code>/login [usuario] [contraseña]</code>\n\n"
                 f"Creator: @{CREATOR_USERNAME}")
            return

        # ── REGISTER (SOLICITUD DE ACCESO) ──
        if text.startswith("/register"):
            parts = text.split()
            if len(parts) != 3:
                send(chat_id,
                     "❌ Uso correcto:\n"
                     "<code>/register [usuario] [contraseña]</code>\n\n"
                     "Ejemplo: <code>/register juan123 mipass456</code>")
                return
            
            username = parts[1]
            password = parts[2]
            
            # Guardar solicitud
            add_request(chat_id, username, password)
            
            # Notificar al usuario
            send(chat_id,
                 f"✅ <b>Solicitud enviada</b>\n\n"
                 f"Usuario: <code>{username}</code>\n"
                 f"Contraseña: <code>{password}</code>\n\n"
                 f"⏳ Espera la aprobación del administrador.")
            
            # Notificar al admin con botones
            keyboard = {
                "inline_keyboard": [
                    [
                        {"text": "✅ Aprobar", "callback_data": f"approve_{chat_id}"},
                        {"text": "❌ Rechazar", "callback_data": f"reject_{chat_id}"}
                    ]
                ]
            }
            
            send(ADMIN_CHAT_ID,
                 f"🔔 <b>NUEVA SOLICITUD DE ACCESO</b>\n"
                 f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
                 f"👤 Telegram: @{telegram_user}\n"
                 f"🆔 Chat ID: <code>{chat_id}</code>\n"
                 f"📝 Usuario: <code>{username}</code>\n"
                 f"🔑 Contraseña: <code>{password}</code>",
                 reply_markup=keyboard)
            return

        # ── LOGIN ──
        if text.startswith("/login"):
            parts = text.split()
            if len(parts) != 3:
                send(chat_id,
                     "❌ Uso correcto:\n"
                     "<code>/login [usuario] [contraseña]</code>")
                return
            
            user, passwd = parts[1], parts[2]
            res = verificar_login(user, passwd)
            
            if res["ok"]:
                send(chat_id,
                     f"✅ Login exitoso\n\n"
                     f"Usuario: <b>{user}</b>\n"
                     f"Lives: <b>{res['data'].get('lives_count', 0)}</b>")
            else:
                send(chat_id, f"❌ {res['error']}")
            return

        # ── ADMIN ONLY ──
        if not is_admin:
            return

        # ── PANEL ──
        if text == "/panel":
            stats = stats_globales()
            pending_count = len(get_all_requests())
            
            msg_text = (
                f"🎛 <b>PANEL DE ADMINISTRACIÓN</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"👥 Total usuarios: <b>{stats['total']}</b>\n"
                f"✅ Activos: <b>{stats['activos']}</b>\n"
                f"💤 Inactivos: <b>{stats['inactivos']}</b>\n"
                f"🚫 Bloqueados: <b>{stats['bloqueados']}</b>\n"
                f"💳 Lives totales: <b>{stats['lives']}</b>\n"
                f"📨 Solicitudes pendientes: <b>{pending_count}</b>\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"<b>COMANDOS</b>\n\n"
                f"/requests — Ver solicitudes pendientes\n"
                f"/users — Ver usuarios\n"
                f"/adduser [user] [pass] — Crear usuario\n"
                f"/block [user] — Bloquear\n"
                f"/unblock [user] — Desbloquear\n"
                f"/delete [user] — Eliminar\n"
                f"/resetpass [user] [pass] — Cambiar contraseña\n"
                f"/logs — Ver logs"
            )
            
            send(chat_id, msg_text)
            return

        # ── REQUESTS ──
        if text == "/requests":
            requests_dict = get_all_requests()
            
            if not requests_dict:
                send(chat_id, "✅ No hay solicitudes pendientes")
                return
            
            msg = "📨 <b>SOLICITUDES PENDIENTES</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
            
            for cid, req in requests_dict.items():
                msg += (f"👤 Chat ID: <code>{cid}</code>\n"
                       f"📝 Usuario: <code>{req['username']}</code>\n"
                       f"🔑 Contraseña: <code>{req['password']}</code>\n"
                       f"⏰ Hace: {int(time.time() - req['timestamp'])}s\n\n")
            
            msg += "\n💡 Usa los botones de las notificaciones o:\n"
            msg += "<code>/approve [chat_id]</code>\n"
            msg += "<code>/reject [chat_id]</code>"
            
            send(chat_id, msg)
            return

        # ── APPROVE ──
        if text.startswith("/approve"):
            parts = text.split()
            if len(parts) != 2:
                send(chat_id, "❌ Uso: /approve [chat_id]")
                return
            
            req_chat_id = parts[1]
            req = get_request(req_chat_id)
            
            if not req:
                send(chat_id, "❌ No hay solicitud para ese chat_id")
                return
            
            try:
                res = registrar_usuario(req['username'], req['password'], "0")
                
                if res["ok"]:
                    send(req_chat_id,
                         f"🎉 <b>¡ACCESO APROBADO!</b>\n\n"
                         f"Tu cuenta ha sido activada:\n"
                         f"Usuario: <code>{req['username']}</code>\n"
                         f"Contraseña: <code>{req['password']}</code>\n\n"
                         f"Usa /login para acceder")
                    
                    send(chat_id,
                         f"✅ Usuario creado y aprobado\n\n"
                         f"Usuario: <code>{req['username']}</code>\n"
                         f"Chat ID: <code>{req_chat_id}</code>")
                    
                    remove_request(req_chat_id)
                else:
                    send(chat_id, f"❌ Error: {res['error']}")
                    
            except Exception as e:
                send(chat_id, f"❌ Error: {str(e)}")
                health.record_error("approve_command", e)
            return

        # ── REJECT ──
        if text.startswith("/reject"):
            parts = text.split()
            if len(parts) != 2:
                send(chat_id, "❌ Uso: /reject [chat_id]")
                return
            
            req_chat_id = parts[1]
            req = get_request(req_chat_id)
            
            if not req:
                send(chat_id, "❌ No hay solicitud para ese chat_id")
                return
            
            send(req_chat_id,
                 f"❌ <b>Solicitud rechazada</b>\n\n"
                 f"Tu solicitud de acceso ha sido rechazada.\n"
                 f"Contacta al administrador si crees que es un error.")
            
            send(chat_id,
                 f"✅ Solicitud rechazada\n\n"
                 f"Usuario: <code>{req['username']}</code>\n"
                 f"Chat ID: <code>{req_chat_id}</code>")
            
            remove_request(req_chat_id)
            return

        # ── USERS ──
        if text == "/users":
            users = obtener_todos_usuarios()
            
            if not users:
                send(chat_id, "❌ No hay usuarios registrados")
                return
            
            msg = "👥 <b>USUARIOS REGISTRADOS</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
            
            for user in users:
                username = user.get('username', 'N/A')
                lives = user.get('lives_count', 0)
                activo = "✅" if user.get('activo') else "💤"
                bloqueado = "🚫" if user.get('bloqueado') else ""
                
                msg += f"{activo}{bloqueado} <b>{username}</b> — {lives} lives\n"
            
            send(chat_id, msg)
            return

        # ── ADD USER ──
        if text.startswith("/adduser"):
            parts = text.split()
            
            if len(parts) == 2:
                from firebase_manager import _generar_password
                user = parts[1]
                p = _generar_password()
            elif len(parts) == 3:
                user, p = parts[1], parts[2]
            else:
                send(chat_id,
                     "❌ Uso:\n"
                     "<code>/adduser [usuario]</code> (genera contraseña)\n"
                     "<code>/adduser [usuario] [contraseña]</code>")
                return
            
            try:
                res = registrar_usuario(user, p, "0")
                
                if res["ok"]:
                    send(chat_id,
                         f"✅ Usuario creado\n\n"
                         f"Usuario: <code>{user}</code>\n"
                         f"Contraseña: <code>{p}</code>")
                else:
                    send(chat_id, f"❌ Error: {res['error']}")
            except Exception as e:
                send(chat_id, f"❌ Error: {str(e)}")
                health.record_error("adduser_command", e)
            return

        # ── BLOCK ──
        if text.startswith("/block"):
            parts = text.split()
            if len(parts) != 2:
                send(chat_id, "❌ Uso: /block [usuario]")
                return
            
            user = parts[1]
            if bloquear_usuario(user):
                send(chat_id, f"✅ Usuario <b>{user}</b> bloqueado")
            else:
                send(chat_id, f"❌ Error bloqueando usuario")
            return

        # ── UNBLOCK ──
        if text.startswith("/unblock"):
            parts = text.split()
            if len(parts) != 2:
                send(chat_id, "❌ Uso: /unblock [usuario]")
                return
            
            user = parts[1]
            if desbloquear_usuario(user):
                send(chat_id, f"✅ Usuario <b>{user}</b> desbloqueado")
            else:
                send(chat_id, f"❌ Error desbloqueando usuario")
            return

        # ── DELETE ──
        if text.startswith("/delete"):
            parts = text.split()
            if len(parts) != 2:
                send(chat_id, "❌ Uso: /delete [usuario]")
                return
            
            user = parts[1]
            if eliminar_usuario(user):
                send(chat_id, f"✅ Usuario <b>{user}</b> eliminado")
            else:
                send(chat_id, f"❌ Error eliminando usuario")
            return

        # ── RESET PASSWORD ──
        if text.startswith("/resetpass"):
            parts = text.split()
            if len(parts) != 3:
                send(chat_id,
                     "❌ Uso: /resetpass [usuario] [nueva_contraseña]\n\n"
                     "Ejemplo: <code>/resetpass juan nuevapass123</code>")
                return
            
            user, new_pass = parts[1], parts[2]
            if cambiar_password(user, new_pass):
                send(chat_id,
                     f"✅ Contraseña actualizada\n\n"
                     f"Usuario: <code>{user}</code>\n"
                     f"Nueva contraseña: <code>{new_pass}</code>")
            else:
                send(chat_id, f"❌ Error cambiando contraseña")
            return

        # ── LOGS ──
        if text == "/logs":
            logs = obtener_logs_recientes(15)
            
            if not logs:
                send(chat_id, "❌ No hay logs disponibles")
                return
            
            msg = "📋 <b>LOGS RECIENTES</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
            
            for log in logs:
                tipo = log.get('tipo', 'N/A')
                data = log.get('data', 'N/A')
                msg += f"• <b>{tipo}</b>: {data}\n"
            
            send(chat_id, msg)
            return

    except Exception as e:
        print(f"❌ Error en handler: {e}")
        print(traceback.format_exc())
        health.record_error("handler", e)
        
        try:
            chat_id = str(msg["chat"]["id"])
            send(chat_id, "❌ Ocurrió un error. Intenta nuevamente.")
        except:
            pass

def handle_callback(callback):
    """Maneja callbacks de botones inline"""
    try:
        data = callback.get("data", "")
        message = callback.get("message", {})
        chat_id = str(message.get("chat", {}).get("id", ""))
        
        if not chat_id or chat_id != ADMIN_CHAT_ID:
            return
        
        # ── APPROVE ──
        if data.startswith("approve_"):
            req_chat_id = data.replace("approve_", "")
            req = get_request(req_chat_id)
            
            if not req:
                send(chat_id, "❌ Solicitud ya procesada o no existe")
                return
            
            try:
                res = registrar_usuario(req['username'], req['password'], "0")
                
                if res["ok"]:
                    send(req_chat_id,
                         f"🎉 <b>¡ACCESO APROBADO!</b>\n\n"
                         f"Tu cuenta ha sido activada:\n"
                         f"Usuario: <code>{req['username']}</code>\n"
                         f"Contraseña: <code>{req['password']}</code>\n\n"
                         f"Usa /login para acceder")
                    
                    send(chat_id,
                         f"✅ <b>SOLICITUD APROBADA</b>\n\n"
                         f"Usuario: <code>{req['username']}</code>\n"
                         f"Chat ID: <code>{req_chat_id}</code>")
                    
                    remove_request(req_chat_id)
                else:
                    send(chat_id, f"❌ Error: {res['error']}")
                    
            except Exception as e:
                send(chat_id, f"❌ Error: {str(e)}")
                health.record_error("callback_approve", e)
        
        # ── REJECT ──
        elif data.startswith("reject_"):
            req_chat_id = data.replace("reject_", "")
            req = get_request(req_chat_id)
            
            if not req:
                send(chat_id, "❌ Solicitud ya procesada o no existe")
                return
            
            send(req_chat_id,
                 f"❌ <b>Solicitud rechazada</b>\n\n"
                 f"Tu solicitud de acceso ha sido rechazada.\n"
                 f"Contacta al administrador si crees que es un error.")
            
            send(chat_id,
                 f"❌ <b>SOLICITUD RECHAZADA</b>\n\n"
                 f"Usuario: <code>{req['username']}</code>\n"
                 f"Chat ID: <code>{req_chat_id}</code>")
            
            remove_request(req_chat_id)
        
    except Exception as e:
        print(f"❌ Error en callback: {e}")
        health.record_error("callback", e)

# ══════════════════════════════════════════════════════════════
# FLASK APP
# ══════════════════════════════════════════════════════════════

app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def webhook():
    """Recibe updates de Telegram via webhook"""
    try:
        update = request.get_json()
        health.update_activity()
        
        if "message" in update:
            handle(update["message"])
        
        if "callback_query" in update:
            handle_callback(update["callback_query"])
            
        return "OK", 200
        
    except Exception as e:
        print(f"❌ Error webhook: {e}")
        print(traceback.format_exc())
        health.record_error("webhook", e)
        return "ERROR", 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check para Koyeb"""
    try:
        stats = health.get_stats()
        return jsonify(stats), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/', methods=['GET'])
def home():
    """Dashboard HTML"""
    try:
        stats = health.get_stats()
        sys_info = get_system_info()
        
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="refresh" content="30">
    <title>𓂀 ANUBIS CHK</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: 'Courier New', monospace;
            background: linear-gradient(135deg, #0a0a0a 0%, #1a1a2e 100%);
            color: #00ff41;
            padding: 20px;
            min-height: 100vh;
        }}
        .container {{
            max-width: 900px;
            margin: 0 auto;
        }}
        .header {{
            text-align: center;
            margin-bottom: 30px;
            padding: 30px;
            background: rgba(0, 255, 65, 0.05);
            border: 2px solid #00ff41;
            border-radius: 15px;
            box-shadow: 0 0 30px rgba(0, 255, 65, 0.3);
        }}
        h1 {{
            font-size: 48px;
            margin-bottom: 10px;
            text-shadow: 0 0 20px rgba(0, 255, 65, 0.5);
        }}
        .subtitle {{
            color: #888;
            font-size: 14px;
        }}
        .badge {{
            display: inline-block;
            padding: 5px 15px;
            margin: 5px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: bold;
            background: rgba(0, 255, 65, 0.2);
            color: #00ff41;
        }}
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }}
        .card {{
            background: rgba(26, 26, 46, 0.8);
            border: 2px solid #00ff41;
            border-radius: 10px;
            padding: 25px;
            backdrop-filter: blur(10px);
            transition: transform 0.3s, box-shadow 0.3s;
        }}
        .card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 10px 30px rgba(0, 255, 65, 0.4);
        }}
        .card-title {{
            font-size: 20px;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 1px solid #00ff41;
            color: #00ff41;
        }}
        .stat {{
            display: flex;
            justify-content: space-between;
            margin: 10px 0;
            padding: 8px 0;
            border-bottom: 1px solid rgba(0, 255, 65, 0.1);
        }}
        .stat-label {{
            color: #888;
        }}
        .stat-value {{
            color: #00ff41;
            font-weight: bold;
        }}
        .footer {{
            text-align: center;
            margin-top: 30px;
            padding: 20px;
            color: #555;
            font-size: 12px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>𓂀 ANUBIS CHK</h1>
            <p class="subtitle">Sistema de Gestión de Usuarios</p>
            <div style="margin-top: 15px;">
                <span class="badge">✅ WEBHOOK MODE</span>
                <span class="badge">🚀 KOYEB OPTIMIZED</span>
                <span class="badge">⚡ NO SLEEP</span>
            </div>
        </div>
        
        <div class="grid">
            <div class="card">
                <div class="card-title">🏥 Estado del Sistema</div>
                <div class="stat">
                    <span class="stat-label">Status:</span>
                    <span class="stat-value">{stats['status'].upper()}</span>
                </div>
                <div class="stat">
                    <span class="stat-label">Uptime:</span>
                    <span class="stat-value">{stats['uptime_formatted']}</span>
                </div>
                <div class="stat">
                    <span class="stat-label">Última actividad:</span>
                    <span class="stat-value">{stats['last_activity']}s</span>
                </div>
            </div>
            
            <div class="card">
                <div class="card-title">📊 Métricas</div>
                <div class="stat">
                    <span class="stat-label">Requests:</span>
                    <span class="stat-value">{stats['requests']}</span>
                </div>
                <div class="stat">
                    <span class="stat-label">Webhooks recibidos:</span>
                    <span class="stat-value">{stats['webhooks_received']}</span>
                </div>
                <div class="stat">
                    <span class="stat-label">Errores (5min):</span>
                    <span class="stat-value">{stats['errors_5min']}</span>
                </div>
                <div class="stat">
                    <span class="stat-label">Errores (15min):</span>
                    <span class="stat-value">{stats['errors_15min']}</span>
                </div>
            </div>
            
            <div class="card">
                <div class="card-title">⚙️ Configuración</div>
                <div class="stat">
                    <span class="stat-label">Admin ID:</span>
                    <span class="stat-value">{sys_info['admin_id']}</span>
                </div>
                <div class="stat">
                    <span class="stat-label">Creator:</span>
                    <span class="stat-value">@{sys_info['creator']}</span>
                </div>
                <div class="stat">
                    <span class="stat-label">Versión:</span>
                    <span class="stat-value">{sys_info['version']}</span>
                </div>
                <div class="stat">
                    <span class="stat-label">Mode:</span>
                    <span class="stat-value">WEBHOOK</span>
                </div>
            </div>
        </div>
        
        <div class="footer">
            © 2025 ANUBIS CHK — Desarrollado por @{sys_info['creator']}<br>
            Auto-refresh cada 30s
        </div>
    </div>
</body>
</html>
        """
        return html
        
    except Exception as e:
        return f"Error: {str(e)}", 500

# ══════════════════════════════════════════════════════════════
# SETUP WEBHOOK
# ══════════════════════════════════════════════════════════════

def setup_webhook():
    """Configura el webhook de Telegram"""
    
    # Obtener URL pública de Koyeb
    webhook_url = os.environ.get("KOYEB_PUBLIC_URL", "")
    
    if not webhook_url:
        print("⚠️ KOYEB_PUBLIC_URL no encontrada en variables de entorno")
        print("⚠️ El bot NO funcionará hasta que configures el webhook manualmente")
        return False
    
    # Añadir ruta del webhook
    if not webhook_url.endswith("/"):
        webhook_url += "/"
    webhook_url += "webhook"
    
    print(f"🔧 Configurando webhook: {webhook_url}")
    
    try:
        # Eliminar webhook anterior (si existe)
        requests.post(
            f"{API}/deleteWebhook",
            timeout=10
        )
        
        time.sleep(1)
        
        # Configurar nuevo webhook
        r = requests.post(
            f"{API}/setWebhook",
            json={"url": webhook_url},
            timeout=10
        )
        
        if r.status_code == 200:
            result = r.json()
            if result.get("ok"):
                print(f"✅ Webhook configurado exitosamente")
                print(f"✅ URL: {webhook_url}")
                
                # Notificar al admin
                try:
                    send(ADMIN_CHAT_ID,
                         "🚀 <b>ANUBIS CHK ONLINE</b>\n\n"
                         "✅ Modo: <b>WEBHOOK</b>\n"
                         "✅ Estado: <b>ACTIVO</b>\n"
                         f"✅ URL: <code>{webhook_url}</code>\n\n"
                         "Panel de control: /panel\n"
                         "Solicitudes: /requests")
                except:
                    pass
                
                return True
            else:
                print(f"❌ Error configurando webhook: {result.get('description')}")
                return False
        else:
            print(f"❌ Error HTTP {r.status_code}: {r.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error configurando webhook: {e}")
        print(traceback.format_exc())
        return False

# ══════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("═" * 60)
    print("🚀 ANUBIS CHK — WEBHOOK MODE")
    print("═" * 60)
    print()
    
    # Esperar a que Koyeb esté listo
    time.sleep(3)
    
    # Configurar webhook
    setup_webhook()
    
    # Iniciar Flask
    port = int(os.environ.get("PORT", 8000))
    print(f"\n🌐 Iniciando Flask en puerto {port}...")
    print("✅ Bot listo para recibir mensajes\n")
    
    app.run(
        host='0.0.0.0',
        port=port,
        debug=False,
        use_reloader=False
    )
