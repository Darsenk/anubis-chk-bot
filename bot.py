"""
═══════════════════════════════════════════════════════════════
ANUBIS CHK BOT — ANTI-CAÍDAS PRO MAX
═══════════════════════════════════════════════════════════════
"""

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
    TELEGRAM_TOKEN,
    ADMIN_CHAT_ID,
    get_db
)

API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# ══════════════════════════════════════════════════════════════
# CONFIGURACIÓN ANTI-CAÍDAS
# ══════════════════════════════════════════════════════════════

class Config:
    # HTTP Server
    HTTP_PORT = int(os.environ.get("PORT", 8000))
    HTTP_TIMEOUT = 30
    
    # Telegram
    POLLING_TIMEOUT = 30
    REQUEST_TIMEOUT = 15
    MAX_RETRIES = 5
    RETRY_DELAY = 3
    
    # Rate limiting
    MAX_REQUESTS_PER_SECOND = 30
    FLOOD_WAIT = 1
    
    # Health monitoring
    HEALTH_CHECK_INTERVAL = 60
    MAX_ERRORS_BEFORE_RESTART = 10
    ERROR_WINDOW = 300  # 5 minutos
    
    # Graceful shutdown
    SHUTDOWN_GRACE_PERIOD = 5


# ══════════════════════════════════════════════════════════════
# SISTEMA DE SALUD Y MONITOREO
# ══════════════════════════════════════════════════════════════

class HealthMonitor:
    def __init__(self):
        self.start_time = time.time()
        self.last_update = time.time()
        self.errors = deque(maxlen=100)
        self.error_lock = Lock()
        self.request_count = 0
        self.last_telegram_response = time.time()
        
    def record_error(self, error_type, details):
        with self.error_lock:
            self.errors.append({
                "type": error_type,
                "details": str(details),
                "timestamp": time.time()
            })
            
    def get_recent_errors(self, window=300):
        """Obtener errores de los últimos N segundos"""
        now = time.time()
        with self.error_lock:
            return [e for e in self.errors if now - e["timestamp"] < window]
    
    def is_healthy(self):
        """Verificar si el bot está saludable"""
        recent_errors = self.get_recent_errors(Config.ERROR_WINDOW)
        
        # Demasiados errores recientes
        if len(recent_errors) > Config.MAX_ERRORS_BEFORE_RESTART:
            return False
            
        # Sin respuesta de Telegram por mucho tiempo
        if time.time() - self.last_telegram_response > 120:
            return False
            
        return True
    
    def update_activity(self):
        self.last_update = time.time()
        self.last_telegram_response = time.time()
        
    def get_stats(self):
        uptime = int(time.time() - self.start_time)
        return {
            "status": "healthy" if self.is_healthy() else "degraded",
            "uptime": uptime,
            "uptime_formatted": f"{uptime//3600}h {(uptime%3600)//60}m {uptime%60}s",
            "requests": self.request_count,
            "errors_5min": len(self.get_recent_errors(300)),
            "last_activity": int(time.time() - self.last_update)
        }


health = HealthMonitor()


# ══════════════════════════════════════════════════════════════
# HTTP SERVER MEJORADO
# ══════════════════════════════════════════════════════════════

class ImprovedHealthCheckHandler(BaseHTTPRequestHandler):
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
            html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>ANUBIS CHK Status</title>
                <style>
                    body {{
                        font-family: monospace;
                        background: #0a0a0a;
                        color: #00ff00;
                        padding: 20px;
                        max-width: 800px;
                        margin: 0 auto;
                    }}
                    .card {{
                        background: #1a1a1a;
                        border: 2px solid #00ff00;
                        border-radius: 10px;
                        padding: 20px;
                        margin: 20px 0;
                    }}
                    h1 {{ color: #00ff00; text-align: center; }}
                    .status {{ font-size: 24px; text-align: center; }}
                    .healthy {{ color: #00ff00; }}
                    .degraded {{ color: #ff0000; }}
                    .stat {{ margin: 10px 0; }}
                    .label {{ color: #888; }}
                </style>
                <script>
                    setTimeout(() => location.reload(), 30000);
                </script>
            </head>
            <body>
                <h1>𓂀 ANUBIS CHK</h1>
                <div class="card">
                    <div class="status {stats['status']}">
                        ● {stats['status'].upper()}
                    </div>
                </div>
                <div class="card">
                    <div class="stat"><span class="label">Uptime:</span> {stats['uptime_formatted']}</div>
                    <div class="stat"><span class="label">Requests:</span> {stats['requests']}</div>
                    <div class="stat"><span class="label">Errors (5min):</span> {stats['errors_5min']}</div>
                    <div class="stat"><span class="label">Last Activity:</span> {stats['last_activity']}s ago</div>
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
    """Servidor HTTP con reintentos automáticos"""
    while True:
        try:
            server = HTTPServer(("0.0.0.0", Config.HTTP_PORT), ImprovedHealthCheckHandler)
            server.timeout = Config.HTTP_TIMEOUT
            print(f"🌐 HTTP Server running on port {Config.HTTP_PORT}")
            server.serve_forever()
        except Exception as e:
            print(f"❌ HTTP Server error: {e}")
            health.record_error("http_server", e)
            time.sleep(5)


# ══════════════════════════════════════════════════════════════
# TELEGRAM API CON RETRY Y RATE LIMITING
# ══════════════════════════════════════════════════════════════

class RateLimiter:
    def __init__(self):
        self.requests = deque()
        self.lock = Lock()
        
    def wait_if_needed(self):
        with self.lock:
            now = time.time()
            # Limpiar requests viejos
            while self.requests and now - self.requests[0] > 1:
                self.requests.popleft()
            
            # Si estamos al límite, esperar
            if len(self.requests) >= Config.MAX_REQUESTS_PER_SECOND:
                time.sleep(Config.FLOOD_WAIT)
                self.requests.clear()
            
            self.requests.append(now)


rate_limiter = RateLimiter()


def telegram_request(method, params=None, data=None, retry=True):
    """Request con retry automático y manejo de errores"""
    rate_limiter.wait_if_needed()
    
    attempts = 0
    last_error = None
    
    while attempts < Config.MAX_RETRIES:
        try:
            url = f"{API}/{method}"
            
            if params:
                response = requests.get(
                    url,
                    params=params,
                    timeout=Config.REQUEST_TIMEOUT
                )
            else:
                response = requests.post(
                    url,
                    data=data,
                    timeout=Config.REQUEST_TIMEOUT
                )
            
            response.raise_for_status()
            health.update_activity()
            health.request_count += 1
            
            result = response.json()
            
            # Manejar errores de Telegram
            if not result.get("ok"):
                error_code = result.get("error_code")
                
                # Retry on flood
                if error_code == 429:
                    retry_after = result.get("parameters", {}).get("retry_after", 5)
                    print(f"⏳ Flood control: waiting {retry_after}s")
                    time.sleep(retry_after)
                    attempts += 1
                    continue
                
                # No retry en errores permanentes
                if error_code in [400, 403, 404]:
                    return result
                    
            return result
            
        except requests.exceptions.Timeout:
            last_error = "timeout"
            print(f"⏱️ Timeout en {method} (intento {attempts + 1}/{Config.MAX_RETRIES})")
            
        except requests.exceptions.ConnectionError:
            last_error = "connection"
            print(f"🔌 Connection error en {method} (intento {attempts + 1}/{Config.MAX_RETRIES})")
            
        except requests.exceptions.RequestException as e:
            last_error = str(e)
            print(f"❌ Request error en {method}: {e}")
            
        except Exception as e:
            last_error = str(e)
            print(f"❌ Unexpected error en {method}: {e}")
            health.record_error(f"telegram_{method}", e)
            
        if not retry:
            break
            
        attempts += 1
        if attempts < Config.MAX_RETRIES:
            time.sleep(Config.RETRY_DELAY * attempts)
    
    # Si llegamos aquí, todos los intentos fallaron
    health.record_error(f"telegram_{method}_failed", last_error)
    return {"ok": False, "error": last_error}


def send(chat_id, text, parse_mode="HTML"):
    """Enviar mensaje con retry automático"""
    return telegram_request("sendMessage", data={
        "chat_id": chat_id,
        "text": text[:4096],  # Telegram limit
        "parse_mode": parse_mode
    })


def get_updates(offset=0):
    """Obtener updates con manejo robusto"""
    result = telegram_request("getUpdates", params={
        "offset": offset,
        "timeout": Config.POLLING_TIMEOUT
    })
    
    if result.get("ok"):
        return result.get("result", [])
    
    return []


# ══════════════════════════════════════════════════════════════
# ESTADOS Y DATOS
# ══════════════════════════════════════════════════════════════

_estados = {}
_pendientes = {}
_estados_lock = Lock()


# ══════════════════════════════════════════════════════════════
# HANDLER CON MANEJO DE ERRORES
# ══════════════════════════════════════════════════════════════

def handle(msg):
    """Handler principal con try-catch comprehensivo"""
    try:
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
                 f"/registro - Registrarse\n"
                 f"/mislives - Ver estadísticas\n"
                 + ("\n/admin - Panel admin" if es_admin else ""))
            return

        # ── PANEL ADMIN ──
        if text == "/admin" and es_admin:
            send(chat_id,
                 "👑 <b>PANEL ADMIN PRO</b>\n\n"
                 "📊 Comandos disponibles:\n\n"
                 "/usuarios - Lista de usuarios\n"
                 "/buscar username - Buscar usuario\n"
                 "/adduser user pass chatid - Crear usuario\n"
                 "/deluser username - Eliminar usuario\n"
                 "/top - Top usuarios\n"
                 "/reset username - Resetear lives\n"
                 "/ban username - Banear usuario\n"
                 "/unban username - Desbanear usuario\n"
                 "/stats - Estadísticas del sistema")
            return

        # ── STATS SISTEMA ──
        if text == "/stats" and es_admin:
            stats = health.get_stats()
            send(chat_id,
                 f"📊 <b>ESTADÍSTICAS DEL SISTEMA</b>\n\n"
                 f"Estado: {stats['status'].upper()}\n"
                 f"Uptime: {stats['uptime_formatted']}\n"
                 f"Requests: {stats['requests']}\n"
                 f"Errores (5min): {stats['errors_5min']}\n"
                 f"Última actividad: {stats['last_activity']}s")
            return

        # ── USUARIOS ──
        if text == "/usuarios" and es_admin:
            users = obtener_todos_usuarios()
            if not users:
                send(chat_id, "📭 No hay usuarios registrados")
                return
                
            txt = "👥 <b>USUARIOS REGISTRADOS</b>\n\n"
            for u in users:
                estado = "🚫" if not u.get('activo', True) else "✅"
                txt += f"{estado} {u['username']} | {u.get('lives_count', 0)} lives\n"
            send(chat_id, txt)
            return

        # ── BUSCAR ──
        if text.startswith("/buscar") and es_admin:
            try:
                parts = text.split(maxsplit=1)
                if len(parts) < 2:
                    send(chat_id, "❌ Uso: /buscar username")
                    return
                    
                user = parts[1]
                db = get_db()
                doc = db.collection("usuarios").document(user.lower()).get()

                if not doc.exists:
                    send(chat_id, f"❌ Usuario '{user}' no existe")
                    return

                u = doc.to_dict()
                send(chat_id,
                     f"👤 <b>INFORMACIÓN DE USUARIO</b>\n\n"
                     f"Username: {u['username']}\n"
                     f"Lives: {u.get('lives_count', 0)}\n"
                     f"Chat ID: {u.get('chat_id')}\n"
                     f"Activo: {'✅ Sí' if u.get('activo', True) else '🚫 No'}\n"
                     f"Bloqueado: {'🔒 Sí' if u.get('bloqueado', False) else '✅ No'}")
            except Exception as e:
                send(chat_id, f"❌ Error: {str(e)}")
                health.record_error("buscar_command", e)
            return

        # ── DELETE ──
        if text.startswith("/deluser") and es_admin:
            try:
                parts = text.split(maxsplit=1)
                if len(parts) < 2:
                    send(chat_id, "❌ Uso: /deluser username")
                    return
                    
                user = parts[1]
                db = get_db()
                db.collection("usuarios").document(user.lower()).delete()
                send(chat_id, f"🗑️ Usuario '{user}' eliminado exitosamente")
            except Exception as e:
                send(chat_id, f"❌ Error: {str(e)}")
                health.record_error("deluser_command", e)
            return

        # ── TOP ──
        if text == "/top" and es_admin:
            try:
                users = obtener_todos_usuarios()
                users = sorted(users, key=lambda x: x.get("lives_count", 0), reverse=True)

                txt = "🏆 <b>TOP USUARIOS</b>\n\n"
                for i, u in enumerate(users[:10], 1):
                    medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
                    txt += f"{medal} {u['username']} → {u.get('lives_count', 0)} lives\n"

                send(chat_id, txt)
            except Exception as e:
                send(chat_id, f"❌ Error: {str(e)}")
                health.record_error("top_command", e)
            return

        # ── RESET ──
        if text.startswith("/reset") and es_admin:
            try:
                parts = text.split(maxsplit=1)
                if len(parts) < 2:
                    send(chat_id, "❌ Uso: /reset username")
                    return
                    
                user = parts[1]
                db = get_db()
                db.collection("usuarios").document(user.lower()).update({
                    "lives_count": 0
                })
                send(chat_id, f"🔄 Lives de '{user}' reseteados a 0")
            except Exception as e:
                send(chat_id, f"❌ Error: {str(e)}")
                health.record_error("reset_command", e)
            return

        # ── BAN ──
        if text.startswith("/ban") and es_admin:
            try:
                parts = text.split(maxsplit=1)
                if len(parts) < 2:
                    send(chat_id, "❌ Uso: /ban username")
                    return
                    
                user = parts[1]
                db = get_db()
                db.collection("usuarios").document(user.lower()).update({
                    "activo": False
                })
                send(chat_id, f"🚫 Usuario '{user}' baneado exitosamente")
            except Exception as e:
                send(chat_id, f"❌ Error: {str(e)}")
                health.record_error("ban_command", e)
            return

        # ── UNBAN ──
        if text.startswith("/unban") and es_admin:
            try:
                parts = text.split(maxsplit=1)
                if len(parts) < 2:
                    send(chat_id, "❌ Uso: /unban username")
                    return
                    
                user = parts[1]
                db = get_db()
                db.collection("usuarios").document(user.lower()).update({
                    "activo": True
                })
                send(chat_id, f"✅ Usuario '{user}' desbaneado exitosamente")
            except Exception as e:
                send(chat_id, f"❌ Error: {str(e)}")
                health.record_error("unban_command", e)
            return

        # ── REGISTRO ──
        if text == "/registro":
            with _estados_lock:
                _estados[chat_id] = {"step": "user"}
            send(chat_id, "👤 Por favor, ingresa tu usuario:")
            return

        # ── FLUJO DE REGISTRO ──
        with _estados_lock:
            estado = _estados.get(chat_id)

        if estado:
            if estado["step"] == "user":
                with _estados_lock:
                    _estados[chat_id] = {"step": "pass", "user": text}
                send(chat_id, "🔑 Ahora ingresa tu contraseña:")
                return

            if estado["step"] == "pass":
                with _estados_lock:
                    _estados[chat_id] = {
                        "step": "confirm",
                        "user": estado["user"],
                        "pass": text
                    }
                send(chat_id,
                     f"📋 <b>Confirma tus datos:</b>\n\n"
                     f"Usuario: {estado['user']}\n"
                     f"Contraseña: {'•' * len(text)}\n\n"
                     f"Responde SI para confirmar o NO para cancelar")
                return

            if estado["step"] == "confirm":
                if text.upper() == "SI":
                    uname = estado["user"]
                    pwd = estado["pass"]

                    db = get_db()
                    if db.collection("usuarios").document(uname.lower()).get().exists:
                        send(chat_id, "❌ Este usuario ya existe")
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

                    send(chat_id, "⏳ Registro enviado. Esperando aprobación del administrador...")

                    send(ADMIN_CHAT_ID,
                         f"🔔 <b>NUEVO REGISTRO</b>\n\n"
                         f"Usuario: {uname}\n"
                         f"Telegram: @{username}\n"
                         f"Chat ID: {chat_id}\n\n"
                         f"/adduser {uname} {pwd} {chat_id}")

                    with _estados_lock:
                        del _estados[chat_id]
                    return
                else:
                    send(chat_id, "❌ Registro cancelado")
                    with _estados_lock:
                        del _estados[chat_id]
                    return

        # ── ADDUSER ──
        if text.startswith("/adduser") and es_admin:
            try:
                parts = text.split()
                if len(parts) != 4:
                    send(chat_id, "❌ Uso: /adduser username password chat_id")
                    return
                    
                _, u, p, cid = parts
                res = registrar_usuario(u, p, cid)

                if res["ok"]:
                    send(chat_id, f"✅ Usuario '{u}' creado exitosamente")
                    send(cid, "🎉 ¡Tu acceso ha sido aprobado! Bienvenido a ANUBIS CHK")
                else:
                    send(chat_id, f"❌ Error: {res['error']}")
            except Exception as e:
                send(chat_id, f"❌ Error: {str(e)}")
                health.record_error("adduser_command", e)
            return

        # ── MIS LIVES ──
        if text == "/mislives":
            try:
                users = obtener_todos_usuarios()
                for u in users:
                    if str(u.get("chat_id")) == chat_id:
                        send(chat_id,
                             f"📊 <b>TUS ESTADÍSTICAS</b>\n\n"
                             f"Usuario: {u['username']}\n"
                             f"Lives encontrados: {u.get('lives_count', 0)}\n"
                             f"Estado: {'✅ Activo' if u.get('activo', True) else '🚫 Inactivo'}")
                        return
                send(chat_id, "❌ No estás registrado. Usa /registro")
            except Exception as e:
                send(chat_id, f"❌ Error: {str(e)}")
                health.record_error("mislives_command", e)
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
# MAIN LOOP CON RECUPERACIÓN AUTOMÁTICA
# ══════════════════════════════════════════════════════════════

shutdown_event = Event()

def signal_handler(signum, frame):
    """Manejo de señales para shutdown graceful"""
    print(f"\n🛑 Señal {signum} recibida. Iniciando shutdown...")
    shutdown_event.set()


def main_loop():
    """Loop principal con manejo robusto de errores"""
    
    # Registrar handlers de señales
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # Iniciar HTTP server
    http_thread = Thread(target=run_http_server, daemon=True)
    http_thread.start()
    
    # Notificar que el bot está online
    try:
        send(ADMIN_CHAT_ID, "🚀 <b>BOT ONLINE</b>\n\nSistema anti-caídas activo")
    except Exception as e:
        print(f"⚠️ No se pudo notificar al admin: {e}")

    offset = 0
    consecutive_errors = 0
    
    print("✅ Bot iniciado. Esperando mensajes...")

    while not shutdown_event.is_set():
        try:
            updates = get_updates(offset)
            
            if updates:
                consecutive_errors = 0  # Reset en operación exitosa
                
                for update in updates:
                    offset = update["update_id"] + 1
                    
                    if "message" in update:
                        try:
                            handle(update["message"])
                        except Exception as e:
                            print(f"❌ Error procesando mensaje: {e}")
                            health.record_error("message_handler", e)
            
            # Verificar salud del sistema
            if not health.is_healthy():
                print("⚠️ Sistema no saludable. Iniciando reinicio...")
                break
                
            time.sleep(0.5)
            
        except KeyboardInterrupt:
            print("\n⚠️ Interrupción de teclado detectada")
            shutdown_event.set()
            break
            
        except Exception as e:
            consecutive_errors += 1
            print(f"❌ Error en loop principal ({consecutive_errors}/{Config.MAX_ERRORS_BEFORE_RESTART}): {e}")
            health.record_error("main_loop", e)
            
            if consecutive_errors >= Config.MAX_ERRORS_BEFORE_RESTART:
                print("💀 Demasiados errores consecutivos. Reiniciando...")
                break
            
            time.sleep(Config.RETRY_DELAY)
    
    # Shutdown graceful
    print("🛑 Iniciando shutdown graceful...")
    try:
        send(ADMIN_CHAT_ID, "⚠️ Bot apagándose...")
    except:
        pass
    
    time.sleep(Config.SHUTDOWN_GRACE_PERIOD)
    print("✅ Shutdown completado")


# ══════════════════════════════════════════════════════════════
# ENTRY POINT CON AUTO-RESTART
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    restart_count = 0
    max_restarts = 100
    
    while restart_count < max_restarts:
        try:
            print(f"\n{'='*60}")
            print(f"🚀 Iniciando bot (restart #{restart_count})")
            print(f"{'='*60}\n")
            
            main_loop()
            
            # Si llegamos aquí, fue shutdown intencional
            if shutdown_event.is_set():
                print("✅ Shutdown intencional. Saliendo...")
                break
            
        except Exception as e:
            print(f"\n💀 CRASH CRÍTICO: {e}")
            print(traceback.format_exc())
            
        restart_count += 1
        
        if restart_count < max_restarts:
            wait_time = min(30, 5 * restart_count)
            print(f"\n⏳ Esperando {wait_time}s antes de reiniciar...")
            time.sleep(wait_time)
        else:
            print(f"\n❌ Límite de reinicios alcanzado ({max_restarts}). Saliendo...")
            
            try:
                send(ADMIN_CHAT_ID, "💀 Bot detenido tras múltiples crashes")
            except:
                pass
