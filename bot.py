"""
═══════════════════════════════════════════════════════════════
ANUBIS CHK BOT — PRO MAX (KOYEB OPTIMIZED)
═══════════════════════════════════════════════════════════════
Bot de Telegram con panel de administrador profesional
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
from threading import Thread, Lock, Event
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
            
        time_since_response = time.time() - self.last_telegram_response
        if time_since_response > 600:
            return False
            
        return True
    
    def update_activity(self):
        self.last_update = time.time()
        self.last_telegram_response = time.time()
        self.successful_polls += 1
        
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
            "last_activity": int(time.time() - self.last_update)
        }

health = HealthMonitor()

# ══════════════════════════════════════════════════════════════
# HTTP SERVER
# ══════════════════════════════════════════════════════════════

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
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
                    .status.healthy {{
                        background: rgba(0, 255, 65, 0.2);
                        border: 1px solid #00ff41;
                        color: #00ff41;
                    }}
                    .status.degraded {{
                        background: rgba(255, 0, 0, 0.2);
                        border: 1px solid #ff0000;
                        color: #ff0000;
                    }}
                    .pulse {{
                        display: inline-block;
                        width: 10px;
                        height: 10px;
                        background: #00ff41;
                        border-radius: 50%;
                        animation: pulse 2s ease-in-out infinite;
                        margin-right: 10px;
                    }}
                    @keyframes pulse {{
                        0%, 100% {{ opacity: 1; transform: scale(1); }}
                        50% {{ opacity: 0.5; transform: scale(1.2); }}
                    }}
                    .footer {{
                        text-align: center;
                        margin-top: 30px;
                        padding: 20px;
                        color: #555;
                        font-size: 12px;
                    }}
                    .creator {{
                        color: #00ff41;
                        text-decoration: none;
                    }}
                </style>
                <script>
                    setTimeout(() => location.reload(), 30000);
                </script>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>𓂀 ANUBIS CHK</h1>
                        <p class="subtitle">Professional Telegram Bot System</p>
                        <p class="subtitle">Version {sys_info['version']}</p>
                    </div>
                    
                    <div class="card" style="text-align: center; margin-bottom: 20px;">
                        <div class="card-title">
                            <span class="pulse"></span>System Status
                        </div>
                        <div class="status {stats['status']}">
                            {stats['status'].upper()}
                        </div>
                    </div>
                    
                    <div class="grid">
                        <div class="card">
                            <div class="card-title">⏱️ Uptime & Activity</div>
                            <div class="stat">
                                <span class="stat-label">Uptime</span>
                                <span class="stat-value">{stats['uptime_formatted']}</span>
                            </div>
                            <div class="stat">
                                <span class="stat-label">Last Activity</span>
                                <span class="stat-value">{stats['last_activity']}s ago</span>
                            </div>
                            <div class="stat">
                                <span class="stat-label">Successful Polls</span>
                                <span class="stat-value">{stats['successful_polls']}</span>
                            </div>
                        </div>
                        
                        <div class="card">
                            <div class="card-title">📊 Performance</div>
                            <div class="stat">
                                <span class="stat-label">Total Requests</span>
                                <span class="stat-value">{stats['requests']}</span>
                            </div>
                            <div class="stat">
                                <span class="stat-label">Errors (5min)</span>
                                <span class="stat-value">{stats['errors_5min']}</span>
                            </div>
                            <div class="stat">
                                <span class="stat-label">Errors (15min)</span>
                                <span class="stat-value">{stats['errors_15min']}</span>
                            </div>
                        </div>
                        
                        <div class="card">
                            <div class="card-title">🔥 Configuration</div>
                            <div class="stat">
                                <span class="stat-label">Firebase Project</span>
                                <span class="stat-value">{sys_info['firebase_project']}</span>
                            </div>
                            <div class="stat">
                                <span class="stat-label">Admin ID</span>
                                <span class="stat-value">{sys_info['admin_id']}</span>
                            </div>
                            <div class="stat">
                                <span class="stat-label">Creator</span>
                                <span class="stat-value">@{sys_info['creator']}</span>
                            </div>
                        </div>
                    </div>
                    
                    <div class="footer">
                        <p>Powered by <a href="https://t.me/{sys_info['creator']}" class="creator">@{sys_info['creator']}</a></p>
                        <p>Auto-refresh every 30 seconds</p>
                    </div>
                </div>
            </body>
            </html>
            """
            self.wfile.write(html.encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):
        pass


def run_http_server():
    max_attempts = 3
    attempt = 0
    
    while attempt < max_attempts:
        try:
            HTTPServer.allow_reuse_address = True
            server = HTTPServer(("0.0.0.0", Config.HTTP_PORT), HealthCheckHandler)
            server.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.timeout = Config.HTTP_TIMEOUT
            
            print(f"🌐 HTTP Server running on port {Config.HTTP_PORT}")
            server.serve_forever()
            
        except OSError as e:
            if "Address already in use" in str(e):
                attempt += 1
                print(f"⚠️ Puerto {Config.HTTP_PORT} en uso. Intento {attempt}/{max_attempts}")
                time.sleep(5)
            else:
                print(f"❌ HTTP Server error: {e}")
                health.record_error("http_server", e)
                break
                
        except Exception as e:
            print(f"❌ HTTP Server error: {e}")
            health.record_error("http_server", e)
            time.sleep(10)

# ══════════════════════════════════════════════════════════════
# TELEGRAM API
# ══════════════════════════════════════════════════════════════

def send(chat_id, text, parse_mode="HTML"):
    for attempt in range(Config.MAX_RETRIES):
        try:
            r = requests.post(
                f"{API}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": parse_mode
                },
                timeout=Config.REQUEST_TIMEOUT
            )
            
            if r.status_code == 200:
                health.request_count += 1
                return True
            elif r.status_code == 429:
                retry_after = r.json().get("parameters", {}).get("retry_after", Config.FLOOD_WAIT)
                time.sleep(retry_after)
            else:
                print(f"⚠️ Error enviando mensaje: {r.status_code}")
                
        except requests.exceptions.Timeout:
            print(f"⏱️ Timeout enviando mensaje (intento {attempt+1}/{Config.MAX_RETRIES})")
        except Exception as e:
            print(f"❌ Error: {e}")
            health.record_error("send_message", e)
            
        if attempt < Config.MAX_RETRIES - 1:
            time.sleep(Config.RETRY_DELAY)
    
    return False


def get_updates(offset=0):
    try:
        r = requests.get(
            f"{API}/getUpdates",
            params={
                "offset": offset,
                "timeout": Config.POLLING_TIMEOUT
            },
            timeout=Config.POLLING_TIMEOUT + 10
        )
        
        if r.status_code == 200:
            result = r.json()
            if result.get("ok"):
                health.update_activity()
                return result.get("result", [])
            else:
                health.record_error("telegram_api", result.get('description'))
        else:
            health.record_error("http_status", r.status_code)
            
    except requests.exceptions.Timeout:
        health.update_activity()
        return []
    except requests.exceptions.ConnectionError as e:
        health.record_error("connection", e)
        time.sleep(5)
    except Exception as e:
        health.record_error("get_updates", e)
        
    return []

# ══════════════════════════════════════════════════════════════
# HANDLER DE MENSAJES
# ══════════════════════════════════════════════════════════════

_estados = {}
_estados_lock = Lock()
_pendientes = {}

def handle(msg):
    try:
        chat_id = str(msg["chat"]["id"])
        username = msg["from"].get("username", "Desconocido")
        text = msg.get("text", "").strip()

        if not text:
            return

        es_admin = (chat_id == ADMIN_CHAT_ID)

        # ══════════════════════════════════════════════════════════
        # COMANDOS BÁSICOS
        # ══════════════════════════════════════════════════════════
        
        if text == "/start":
            send(chat_id,
                 "𓂀 <b>ANUBIS CHK PRO</b>\n\n"
                 "🔐 <b>Comandos Disponibles:</b>\n"
                 "━━━━━━━━━━━━━━━━━━━━━━\n"
                 "/login - Iniciar sesión\n"
                 "/registro - Crear cuenta nueva\n"
                 "/mislives - Ver tus estadísticas\n"
                 "/help - Ayuda y comandos\n\n"
                 f"🏆 Creado por @{CREATOR_USERNAME}")
            return

        if text == "/help":
            help_text = (
                "📖 <b>GUÍA DE USO</b>\n\n"
                "<b>1. Registro:</b>\n"
                "   • Usa /registro para crear tu cuenta\n"
                "   • Espera aprobación del administrador\n\n"
                "<b>2. Login:</b>\n"
                "   • Usa /login para acceder\n"
                "   • Ingresa usuario y contraseña\n\n"
                "<b>3. Estadísticas:</b>\n"
                "   • /mislives para ver tus stats\n\n"
            )
            
            if es_admin:
                help_text += (
                    "\n🔧 <b>COMANDOS DE ADMIN:</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━━━\n"
                    "/panel - Panel de administración\n"
                    "/stats - Estadísticas globales\n"
                    "/users - Lista de usuarios\n"
                    "/adduser - Agregar usuario\n"
                    "/block [usuario] - Bloquear\n"
                    "/unblock [usuario] - Desbloquear\n"
                    "/delete [usuario] - Eliminar\n"
                    "/resetpass [usuario] [nueva_clave]\n"
                    "/logs - Ver logs recientes\n"
                )
            
            send(chat_id, help_text)
            return

        # ══════════════════════════════════════════════════════════
        # REGISTRO
        # ══════════════════════════════════════════════════════════
        
        if text == "/registro":
            with _estados_lock:
                _estados[chat_id] = {"paso": "username"}
            send(chat_id,
                 "📝 <b>REGISTRO DE CUENTA</b>\n\n"
                 "Por favor, ingresa un nombre de usuario:")
            return

        # Proceso de registro
        with _estados_lock:
            estado = _estados.get(chat_id)

        if estado:
            if estado["paso"] == "username":
                uname = text
                with _estados_lock:
                    _estados[chat_id] = {"paso": "password", "username": uname}
                send(chat_id, "🔐 Ahora ingresa una contraseña segura:")
                return

            elif estado["paso"] == "password":
                pwd = text
                uname = estado["username"]

                with _estados_lock:
                    _estados[chat_id] = {"paso": "confirmar", "username": uname, "password": pwd}

                send(chat_id,
                     f"✅ <b>CONFIRMA TU REGISTRO</b>\n\n"
                     f"👤 Usuario: <code>{uname}</code>\n"
                     f"🔑 Contraseña: <code>{pwd}</code>\n\n"
                     f"¿Los datos son correctos?\n"
                     f"Responde <b>SI</b> para confirmar o <b>NO</b> para cancelar")
                return

            elif estado["paso"] == "confirmar":
                if text.upper() == "SI":
                    uname = estado["username"]
                    pwd = estado["password"]

                    usuarios = obtener_todos_usuarios()
                    for u in usuarios:
                        if u.get("username", "").lower() == uname.lower():
                            send(chat_id, "❌ Este usuario ya existe. Intenta con otro nombre.")
                            with _estados_lock:
                                del _estados[chat_id]
                            return

                    with _estados_lock:
                        _pendientes[chat_id] = {
                            "username": uname,
                            "password": pwd,
                            "chat_id": chat_id,
                            "telegram_user": username
                        }

                    send(chat_id,
                         "⏳ <b>Registro enviado</b>\n\n"
                         "Tu solicitud ha sido enviada al administrador.\n"
                         "Te notificaremos cuando sea aprobada. ⏰")

                    send(ADMIN_CHAT_ID,
                         f"🔔 <b>NUEVA SOLICITUD DE REGISTRO</b>\n\n"
                         f"👤 Usuario: <code>{uname}</code>\n"
                         f"📱 Telegram: @{username}\n"
                         f"🆔 Chat ID: <code>{chat_id}</code>\n\n"
                         f"<b>Aprobar:</b>\n"
                         f"<code>/adduser {uname} {pwd} {chat_id}</code>")

                    with _estados_lock:
                        del _estados[chat_id]
                    return
                else:
                    send(chat_id, "❌ Registro cancelado")
                    with _estados_lock:
                        del _estados[chat_id]
                    return

        # ══════════════════════════════════════════════════════════
        # MIS LIVES
        # ══════════════════════════════════════════════════════════
        
        if text == "/mislives":
            try:
                usuario = get_usuario_por_chat(chat_id)
                
                if not usuario:
                    send(chat_id,
                         "❌ No estás registrado\n\n"
                         "Usa /registro para crear una cuenta")
                    return

                send(chat_id,
                     f"📊 <b>TUS ESTADÍSTICAS</b>\n"
                     f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
                     f"👤 Usuario: <code>{usuario['username']}</code>\n"
                     f"💎 Lives encontrados: <b>{usuario.get('lives_count', 0)}</b>\n"
                     f"📈 Estado: {'✅ Activo' if usuario.get('activo', True) else '🚫 Inactivo'}\n\n"
                     f"¡Sigue buscando! 🔍")
            except Exception as e:
                send(chat_id, f"❌ Error: {str(e)}")
                health.record_error("mislives_command", e)
            return

        # ══════════════════════════════════════════════════════════
        # COMANDOS DE ADMIN
        # ══════════════════════════════════════════════════════════
        
        if not es_admin:
            return

        # ── PANEL ──
        if text == "/panel":
            stats = stats_globales()
            send(chat_id,
                 f"🔧 <b>PANEL DE ADMINISTRACIÓN</b>\n"
                 f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
                 f"👥 Total usuarios: <b>{stats.get('total', 0)}</b>\n"
                 f"✅ Activos: <b>{stats.get('activos', 0)}</b>\n"
                 f"🚫 Inactivos: <b>{stats.get('inactivos', 0)}</b>\n"
                 f"🔒 Bloqueados: <b>{stats.get('bloqueados', 0)}</b>\n"
                 f"💎 Total Lives: <b>{stats.get('lives', 0)}</b>\n\n"
                 f"<b>Comandos disponibles:</b>\n"
                 f"/users - Ver todos los usuarios\n"
                 f"/stats - Estadísticas detalladas\n"
                 f"/logs - Ver logs recientes\n"
                 f"/adduser - Agregar usuario\n"
                 f"/block [user] - Bloquear\n"
                 f"/unblock [user] - Desbloquear\n"
                 f"/delete [user] - Eliminar\n"
                 f"/resetpass [user] [pass]")
            return

        # ── STATS ──
        if text == "/stats":
            stats = stats_globales()
            usuarios = obtener_todos_usuarios()
            
            top_lives = sorted(usuarios, key=lambda x: x.get('lives_count', 0), reverse=True)[:5]
            
            msg = (
                f"📊 <b>ESTADÍSTICAS GLOBALES</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"👥 Total usuarios: <b>{stats.get('total', 0)}</b>\n"
                f"✅ Activos: <b>{stats.get('activos', 0)}</b>\n"
                f"🚫 Inactivos: <b>{stats.get('inactivos', 0)}</b>\n"
                f"🔒 Bloqueados: <b>{stats.get('bloqueados', 0)}</b>\n"
                f"💎 Total Lives: <b>{stats.get('lives', 0)}</b>\n\n"
                f"<b>🏆 Top 5 Lives:</b>\n"
            )
            
            for i, u in enumerate(top_lives, 1):
                emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "  "
                msg += f"{emoji} {u.get('username', 'N/A')}: {u.get('lives_count', 0)}\n"
            
            send(chat_id, msg)
            return

        # ── USERS ──
        if text == "/users":
            usuarios = obtener_todos_usuarios()
            
            if not usuarios:
                send(chat_id, "❌ No hay usuarios registrados")
                return
            
            msg = f"👥 <b>LISTA DE USUARIOS ({len(usuarios)})</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
            
            for u in usuarios[:20]:  # Limitar a 20 para no exceder límite de mensaje
                estado = "✅" if u.get('activo') else "🚫"
                bloqueado = "🔒" if u.get('bloqueado') else ""
                msg += (
                    f"{estado} {bloqueado} <b>{u.get('username', 'N/A')}</b>\n"
                    f"   💎 Lives: {u.get('lives_count', 0)} | "
                    f"ID: <code>{u.get('chat_id', 'N/A')}</code>\n\n"
                )
            
            if len(usuarios) > 20:
                msg += f"\n... y {len(usuarios) - 20} usuarios más"
            
            send(chat_id, msg)
            return

        # ── ADD USER ──
        if text.startswith("/adduser"):
            try:
                parts = text.split()
                if len(parts) != 4:
                    send(chat_id,
                         "❌ <b>Uso incorrecto</b>\n\n"
                         "Formato: /adduser [usuario] [contraseña] [chat_id]\n\n"
                         "Ejemplo:\n"
                         "<code>/adduser juan pass123 987654321</code>")
                    return
                    
                _, u, p, cid = parts
                res = registrar_usuario(u, p, cid)

                if res["ok"]:
                    send(chat_id, f"✅ Usuario <b>{u}</b> creado exitosamente")
                    send(cid,
                         f"🎉 <b>¡BIENVENIDO A ANUBIS CHK!</b>\n\n"
                         f"Tu cuenta ha sido aprobada.\n"
                         f"Ya puedes usar /login para acceder.\n\n"
                         f"Usuario: <code>{u}</code>\n"
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
    
    http_thread = Thread(target=run_http_server, daemon=True)
    http_thread.start()
    
    if Config.NOTIFY_RESTARTS:
        try:
            send(ADMIN_CHAT_ID,
                 "🚀 <b>ANUBIS CHK ONLINE</b>\n\n"
                 f"Panel de control: /panel")
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
