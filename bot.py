"""
═══════════════════════════════════════════════════════════════
ANUBIS CHK BOT — PRO MAX (KOYEB OPTIMIZED - FIXED)
═══════════════════════════════════════════════════════════════
Bot de Telegram con panel de administrador profesional
Con sistema de solicitud de acceso
═══════════════════════════════════════════════════════════════
"""
import socket
import os
import sys
import time
import json
import requests
import signal
import traceback
from threading import Thread, Lock, Event, Timer
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
from collections import deque

_BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _BASE)

from firebase_manager import (
    registrar_usuario,
    verificar_login,
    obtener_todos_usuarios,
    get_usuario_por_chat,
    actualizar_lives,
    stats_globales,
    bloquear_usuario,
    desbloquear_usuario,
    activar_usuario,
    desactivar_usuario,
    eliminar_usuario,
    cambiar_password,
    obtener_logs_recientes,
    get_system_info,
    TELEGRAM_TOKEN,
    ADMIN_CHAT_ID,
    CREATOR_USERNAME,
    get_db
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
            "telegram_username": None
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
# CONFIGURACIÓN KOYEB
# ══════════════════════════════════════════════════════════════

class Config:
    HTTP_PORT = int(os.environ.get("PORT", 8000))
    HTTP_TIMEOUT = 30
    POLLING_TIMEOUT = 90
    REQUEST_TIMEOUT = 45
    MAX_RETRIES = 5
    RETRY_DELAY = 10
    MAX_REQUESTS_PER_SECOND = 30
    FLOOD_WAIT = 1
    HEALTH_CHECK_INTERVAL = 120
    MAX_ERRORS_BEFORE_RESTART = 25
    ERROR_WINDOW = 900
    SHUTDOWN_GRACE_PERIOD = 5
    NOTIFY_RESTARTS = True
    KEEPALIVE_INTERVAL = 240  # 4 minutos - envía actividad cada 4 min
    IDLE_TIMEOUT = 600  # 10 minutos sin actividad = problema

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
        self.last_telegram_response = time.time()
        self.successful_polls = 0
        self.last_keepalive = time.time()
        
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
    
    def is_healthy(self):
        recent_errors = self.get_recent_errors(Config.ERROR_WINDOW)
        
        if len(recent_errors) > Config.MAX_ERRORS_BEFORE_RESTART:
            return False
            
        # CORREGIDO: Aumentar timeout a 15 minutos (900s)
        time_since_response = time.time() - self.last_telegram_response
        if time_since_response > 900:
            print(f"⚠️ Sin respuesta de Telegram desde hace {int(time_since_response)}s")
            return False
            
        return True
    
    def update_activity(self):
        self.last_update = time.time()
        self.last_telegram_response = time.time()
        self.successful_polls += 1
        
    def keepalive(self):
        """Marca actividad para evitar timeouts"""
        self.last_keepalive = time.time()
        
    def get_stats(self):
        uptime = int(time.time() - self.start_time)
        return {
            "status": "healthy" if self.is_healthy() else "degraded",
            "uptime": uptime,
            "uptime_formatted": f"{uptime//3600}h {(uptime%3600)//60}m {uptime%60}s",
            "requests": self.request_count,
            "successful_polls": self.successful_polls,
            "errors_5min": len(self.get_recent_errors(300)),
            "errors_15min": len(self.get_recent_errors(900)),
            "last_activity": int(time.time() - self.last_update),
            "last_keepalive": int(time.time() - self.last_keepalive)
        }

health = HealthMonitor()

# ══════════════════════════════════════════════════════════════
# HTTP SERVER
# ══════════════════════════════════════════════════════════════

class HealthCheckHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Silenciar logs HTTP
        
    def do_GET(self):
        # IMPORTANTE: Registrar actividad en cada health check
        health.keepalive()
        
        if self.path == "/health":
            stats = health.get_stats()
            
            if stats["status"] == "healthy":
                self.send_response(200)
            else:
                self.send_response(503)
                
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(stats, indent=2).encode())
            
        elif self.path == "/":
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            
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
                    .status {{
                        display: inline-block;
                        padding: 5px 15px;
                        border-radius: 20px;
                        font-weight: bold;
                    }}
                    .status-healthy {{
                        background: rgba(0, 255, 65, 0.2);
                        color: #00ff41;
                    }}
                    .status-degraded {{
                        background: rgba(255, 165, 0, 0.2);
                        color: #ffa500;
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
                        <p class="subtitle">Auto-refresh cada 30s</p>
                    </div>
                    
                    <div class="grid">
                        <div class="card">
                            <div class="card-title">🏥 Estado del Sistema</div>
                            <div class="stat">
                                <span class="stat-label">Status:</span>
                                <span class="status status-{stats['status']}">{stats['status'].upper()}</span>
                            </div>
                            <div class="stat">
                                <span class="stat-label">Uptime:</span>
                                <span class="stat-value">{stats['uptime_formatted']}</span>
                            </div>
                            <div class="stat">
                                <span class="stat-label">Última actividad:</span>
                                <span class="stat-value">{stats['last_activity']}s</span>
                            </div>
                            <div class="stat">
                                <span class="stat-label">Último keepalive:</span>
                                <span class="stat-value">{stats['last_keepalive']}s</span>
                            </div>
                        </div>
                        
                        <div class="card">
                            <div class="card-title">📊 Métricas</div>
                            <div class="stat">
                                <span class="stat-label">Requests:</span>
                                <span class="stat-value">{stats['requests']}</span>
                            </div>
                            <div class="stat">
                                <span class="stat-label">Polls exitosos:</span>
                                <span class="stat-value">{stats['successful_polls']}</span>
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
                                <span class="stat-label">Firebase:</span>
                                <span class="stat-value">{sys_info['firebase_project']}</span>
                            </div>
                        </div>
                    </div>
                    
                    <div class="footer">
                        © 2025 ANUBIS CHK — Desarrollado por @{sys_info['creator']}
                    </div>
                </div>
            </body>
            </html>
            """
            self.wfile.write(html.encode())
        else:
            self.send_response(404)
            self.end_headers()

def run_http_server():
    """Ejecuta el servidor HTTP con reintentos"""
    max_retries = 10
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            server = HTTPServer(('0.0.0.0', Config.HTTP_PORT), HealthCheckHandler)
            server.timeout = Config.HTTP_TIMEOUT
            print(f"🌐 HTTP Server running on port {Config.HTTP_PORT}")
            server.serve_forever()
            
        except OSError as e:
            if "Address already in use" in str(e):
                retry_count += 1
                print(f"⚠️ Puerto {Config.HTTP_PORT} ocupado. Reintento {retry_count}/{max_retries}")
                time.sleep(5)
            else:
                print(f"❌ Error HTTP: {e}")
                break
        except Exception as e:
            print(f"❌ Error crítico en HTTP server: {e}")
            break

# ══════════════════════════════════════════════════════════════
# TELEGRAM API
# ══════════════════════════════════════════════════════════════

def get_updates(offset=0):
    """Obtiene actualizaciones de Telegram"""
    try:
        health.request_count += 1
        
        r = requests.get(
            f"{API}/getUpdates",
            params={
                "offset": offset,
                "timeout": Config.POLLING_TIMEOUT
            },
            timeout=Config.REQUEST_TIMEOUT
        )
        
        if r.status_code == 200:
            data = r.json()
            if data.get("ok"):
                health.update_activity()
                return data.get("result", [])
        
        return []
        
    except requests.exceptions.Timeout:
        # Timeout normal del long polling, no es error
        health.update_activity()
        return []
    except Exception as e:
        print(f"⚠️ Error get_updates: {e}")
        health.record_error("get_updates", e)
        return []

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
            timeout=Config.REQUEST_TIMEOUT
        )
        
        if r.status_code == 200:
            health.update_activity()
            return True
            
        return False
        
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

        # ── REQUESTS (VER SOLICITUDES PENDIENTES) ──
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

        # ── APPROVE (APROBAR SOLICITUD) ──
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
            
            # Crear usuario
            try:
                res = registrar_usuario(req['username'], req['password'], "0")
                
                if res["ok"]:
                    # Notificar al usuario
                    send(req_chat_id,
                         f"🎉 <b>¡ACCESO APROBADO!</b>\n\n"
                         f"Tu cuenta ha sido activada:\n"
                         f"Usuario: <code>{req['username']}</code>\n"
                         f"Contraseña: <code>{req['password']}</code>\n\n"
                         f"Usa /login para acceder")
                    
                    # Notificar al admin
                    send(chat_id,
                         f"✅ Usuario creado y aprobado\n\n"
                         f"Usuario: <code>{req['username']}</code>\n"
                         f"Chat ID: <code>{req_chat_id}</code>")
                    
                    # Eliminar solicitud
                    remove_request(req_chat_id)
                else:
                    send(chat_id, f"❌ Error creando usuario: {res['error']}")
                    
            except Exception as e:
                send(chat_id, f"❌ Error: {str(e)}")
                health.record_error("approve_command", e)
            return

        # ── REJECT (RECHAZAR SOLICITUD) ──
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
            
            # Notificar al usuario
            send(req_chat_id,
                 f"❌ <b>Solicitud rechazada</b>\n\n"
                 f"Tu solicitud de acceso ha sido rechazada.\n"
                 f"Contacta al administrador si crees que es un error.")
            
            # Notificar al admin
            send(chat_id,
                 f"✅ Solicitud rechazada\n\n"
                 f"Usuario: <code>{req['username']}</code>\n"
                 f"Chat ID: <code>{req_chat_id}</code>")
            
            # Eliminar solicitud
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
                # Solo username, generar password
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
        callback_id = callback.get("id")
        data = callback.get("data", "")
        message = callback.get("message", {})
        chat_id = str(message.get("chat", {}).get("id", ""))
        
        if not chat_id or chat_id != ADMIN_CHAT_ID:
            return
        
        # Parsear callback data
        if data.startswith("approve_"):
            req_chat_id = data.replace("approve_", "")
            req = get_request(req_chat_id)
            
            if not req:
                send(chat_id, "❌ Solicitud ya procesada o no existe")
                return
            
            # Crear usuario
            try:
                res = registrar_usuario(req['username'], req['password'], "0")
                
                if res["ok"]:
                    # Notificar al usuario
                    send(req_chat_id,
                         f"🎉 <b>¡ACCESO APROBADO!</b>\n\n"
                         f"Tu cuenta ha sido activada:\n"
                         f"Usuario: <code>{req['username']}</code>\n"
                         f"Contraseña: <code>{req['password']}</code>\n\n"
                         f"Usa /login para acceder")
                    
                    # Editar mensaje original
                    send(chat_id,
                         f"✅ <b>SOLICITUD APROBADA</b>\n\n"
                         f"Usuario: <code>{req['username']}</code>\n"
                         f"Chat ID: <code>{req_chat_id}</code>")
                    
                    # Eliminar solicitud
                    remove_request(req_chat_id)
                else:
                    send(chat_id, f"❌ Error: {res['error']}")
                    
            except Exception as e:
                send(chat_id, f"❌ Error: {str(e)}")
                health.record_error("callback_approve", e)
        
        elif data.startswith("reject_"):
            req_chat_id = data.replace("reject_", "")
            req = get_request(req_chat_id)
            
            if not req:
                send(chat_id, "❌ Solicitud ya procesada o no existe")
                return
            
            # Notificar al usuario
            send(req_chat_id,
                 f"❌ <b>Solicitud rechazada</b>\n\n"
                 f"Tu solicitud de acceso ha sido rechazada.\n"
                 f"Contacta al administrador si crees que es un error.")
            
            # Editar mensaje
            send(chat_id,
                 f"❌ <b>SOLICITUD RECHAZADA</b>\n\n"
                 f"Usuario: <code>{req['username']}</code>\n"
                 f"Chat ID: <code>{req_chat_id}</code>")
            
            # Eliminar solicitud
            remove_request(req_chat_id)
        
    except Exception as e:
        print(f"❌ Error en callback: {e}")
        health.record_error("callback", e)

# ══════════════════════════════════════════════════════════════
# KEEPALIVE AUTOMÁTICO
# ══════════════════════════════════════════════════════════════

def keepalive_loop():
    """Thread que envía pings periódicos para mantener vivo el bot"""
    while not shutdown_event.is_set():
        try:
            time.sleep(Config.KEEPALIVE_INTERVAL)
            
            # Verificar conectividad
            health.keepalive()
            
            # Enviar ping silencioso a Telegram
            requests.get(
                f"{API}/getMe",
                timeout=10
            )
            
            print(f"💚 Keepalive OK (uptime: {int(time.time() - health.start_time)}s)")
            
        except Exception as e:
            print(f"⚠️ Keepalive error: {e}")

# ══════════════════════════════════════════════════════════════
# MAIN LOOP
# ══════════════════════════════════════════════════════════════

shutdown_event = Event()

def signal_handler(signum, frame):
    print(f"\n🛑 Señal {signum} recibida. Iniciando shutdown...")
    shutdown_event.set()


def main_loop():
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # Iniciar HTTP server
    http_thread = Thread(target=run_http_server, daemon=True)
    http_thread.start()
    
    # NUEVO: Iniciar keepalive thread
    keepalive_thread = Thread(target=keepalive_loop, daemon=True)
    keepalive_thread.start()
    
    if Config.NOTIFY_RESTARTS:
        try:
            send(ADMIN_CHAT_ID,
                 "🚀 <b>ANUBIS CHK ONLINE</b>\n\n"
                 f"Panel de control: /panel\n"
                 f"Solicitudes: /requests\n"
                 f"Keepalive: cada {Config.KEEPALIVE_INTERVAL}s")
        except Exception as e:
            print(f"⚠️ No se pudo notificar al admin: {e}")
    
    print("✅ Bot iniciado. Esperando mensajes...")

    offset = 0
    consecutive_errors = 0
    health_check_counter = 0
    
    while not shutdown_event.is_set():
        try:
            updates = get_updates(offset)
            
            if updates:
                consecutive_errors = 0
                
                for update in updates:
                    offset = update["update_id"] + 1
                    
                    if "message" in update:
                        try:
                            handle(update["message"])
                        except Exception as e:
                            print(f"❌ Error procesando mensaje: {e}")
                            health.record_error("message_handler", e)
                    
                    # Manejar callbacks de botones
                    if "callback_query" in update:
                        try:
                            handle_callback(update["callback_query"])
                        except Exception as e:
                            print(f"❌ Error procesando callback: {e}")
                            health.record_error("callback_handler", e)
            
            # Check de salud cada ~2 minutos (240 * 0.5s = 120s)
            health_check_counter += 1
            if health_check_counter >= 240:
                health_check_counter = 0
                
                if not health.is_healthy():
                    print("⚠️ Sistema no saludable detectado")
                    time.sleep(60)
                    
                    if not health.is_healthy():
                        print("💀 Sistema sigue no saludable. Reiniciando...")
                        break
            
            time.sleep(0.5)
            
        except KeyboardInterrupt:
            print("\n⚠️ Interrupción de teclado detectada")
            shutdown_event.set()
            break
            
        except Exception as e:
            consecutive_errors += 1
            print(f"❌ Error en loop ({consecutive_errors}/{Config.MAX_ERRORS_BEFORE_RESTART}): {e}")
            health.record_error("main_loop", e)
            
            if consecutive_errors >= Config.MAX_ERRORS_BEFORE_RESTART:
                print("💀 Demasiados errores consecutivos. Reiniciando...")
                break
            
            time.sleep(Config.RETRY_DELAY * min(consecutive_errors, 5))
    
    print("🛑 Iniciando shutdown graceful...")
    
    if Config.NOTIFY_RESTARTS:
        try:
            send(ADMIN_CHAT_ID, "⚠️ Bot apagándose...")
        except:
            pass
    
    time.sleep(Config.SHUTDOWN_GRACE_PERIOD)
    print("✅ Shutdown completado")


# ══════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    restart_count = 0
    max_restarts = 5
    last_start = time.time()
    
    while restart_count < max_restarts:
        try:
            print(f"\n{'='*60}")
            print(f"🚀 Iniciando ANUBIS CHK (restart #{restart_count})")
            print(f"{'='*60}\n")
            
            main_loop()
            
            if shutdown_event.is_set():
                print("✅ Shutdown intencional. Saliendo...")
                break
            
        except Exception as e:
            print(f"\n💀 CRASH CRÍTICO: {e}")
            print(traceback.format_exc())
            
        restart_count += 1
        
        uptime = time.time() - last_start
        if uptime < 60:
            wait_time = 30
            print(f"\n⚠️ Restart muy rápido (uptime: {int(uptime)}s). Esperando {wait_time}s...")
            time.sleep(wait_time)
        
        if restart_count < max_restarts:
            wait_time = min(60, 10 * restart_count)
            print(f"\n⏳ Esperando {wait_time}s antes de reiniciar...")
            time.sleep(wait_time)
            last_start = time.time()
        else:
            print(f"\n❌ Límite de reinicios alcanzado ({max_restarts}). Saliendo...")
            
            if Config.NOTIFY_RESTARTS:
                try:
                    send(ADMIN_CHAT_ID, "💀 Bot detenido tras múltiples crashes")
                except:
                    pass
