"""
═══════════════════════════════════════════════════════════════
ANUBIS CHK BOT — VERSIÓN ESTABLE CORREGIDA
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
    TELEGRAM_TOKEN,
    ADMIN_CHAT_ID,
    get_db
)

API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# ══════════════════════════════════════════════════════════════
# CONFIGURACIÓN OPTIMIZADA PARA KOYEB
# ══════════════════════════════════════════════════════════════

class Config:
    # HTTP Server
    HTTP_PORT = int(os.environ.get("PORT", 8000))
    HTTP_TIMEOUT = 30
    
    # Telegram - AJUSTADO PARA MAYOR ESTABILIDAD
    POLLING_TIMEOUT = 90  # Aumentado a 90 segundos
    REQUEST_TIMEOUT = 45  # Aumentado a 45 segundos
    MAX_RETRIES = 5  # Aumentado a 5 para dar más tiempo
    RETRY_DELAY = 10  # Aumentado a 10 segundos entre reintentos
    
    # Rate limiting
    MAX_REQUESTS_PER_SECOND = 30
    FLOOD_WAIT = 1
    
    # Health monitoring - MENOS SENSIBLE
    HEALTH_CHECK_INTERVAL = 120  # Cada 2 minutos
    MAX_ERRORS_BEFORE_RESTART = 25  # Aumentado de 15 a 25
    ERROR_WINDOW = 900  # 15 minutos (antes 10)
    
    # Graceful shutdown
    SHUTDOWN_GRACE_PERIOD = 5
    
    # Notificaciones - SOLO CUANDO ES NECESARIO
    NOTIFY_RESTARTS = False  # Cambiar a True solo si quieres notificaciones


# ══════════════════════════════════════════════════════════════
# SISTEMA DE SALUD Y MONITOREO - MEJORADO
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
        """Obtener errores de los últimos N segundos"""
        now = time.time()
        with self.error_lock:
            return [e for e in self.errors if now - e["timestamp"] < window]
    
    def is_healthy(self):
        """Verificar si el bot está saludable - MENOS ESTRICTO"""
        recent_errors = self.get_recent_errors(Config.ERROR_WINDOW)
        
        # Demasiados errores recientes
        if len(recent_errors) > Config.MAX_ERRORS_BEFORE_RESTART:
            print(f"⚠️ Demasiados errores: {len(recent_errors)}/{Config.MAX_ERRORS_BEFORE_RESTART}")
            return False
            
        # Sin respuesta de Telegram por MUCHO tiempo - AUMENTADO
        time_since_response = time.time() - self.last_telegram_response
        if time_since_response > 600:  # 10 minutos (antes 5)
            print(f"⚠️ Sin respuesta de Telegram por {int(time_since_response)}s")
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
                    setTimeout(() => location.reload(), 60000);
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
                    <div class="stat"><span class="label">Successful Polls:</span> {stats['successful_polls']}</div>
                    <div class="stat"><span class="label">Errors (5min):</span> {stats['errors_5min']}</div>
                    <div class="stat"><span class="label">Errors (15min):</span> {stats['errors_15min']}</div>
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
    """Servidor HTTP con reintentos automáticos y mejor manejo de errores"""
    max_attempts = 3
    attempt = 0
    
    while attempt < max_attempts:
        try:
            # Configurar servidor con opciones para evitar conflictos
            HTTPServer.allow_reuse_address = True
            server = HTTPServer(("0.0.0.0", Config.HTTP_PORT), ImprovedHealthCheckHandler)
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
# TELEGRAM API — CON RETRY MEJORADO
# ══════════════════════════════════════════════════════════════

def send(chat_id, text, parse_mode="HTML"):
    """Enviar mensaje con retry y mejor manejo de errores"""
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
                # Rate limit
                retry_after = r.json().get("parameters", {}).get("retry_after", Config.FLOOD_WAIT)
                print(f"⏳ Rate limit. Esperando {retry_after}s...")
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
    """Obtener actualizaciones con mejor manejo de timeouts"""
    try:
        r = requests.get(
            f"{API}/getUpdates",
            params={
                "offset": offset,
                "timeout": Config.POLLING_TIMEOUT
            },
            timeout=Config.POLLING_TIMEOUT + 10  # +10s de margen
        )
        
        if r.status_code == 200:
            result = r.json()
            if result.get("ok"):
                health.update_activity()
                return result.get("result", [])
            else:
                print(f"⚠️ Telegram API error: {result.get('description')}")
                health.record_error("telegram_api", result.get('description'))
        else:
            print(f"⚠️ HTTP {r.status_code}")
            health.record_error("http_status", r.status_code)
            
    except requests.exceptions.Timeout:
        # Los timeouts son normales en long polling
        health.update_activity()
        return []
    except requests.exceptions.ConnectionError as e:
        print(f"⚠️ Error de conexión: {e}")
        health.record_error("connection", e)
        time.sleep(5)
    except Exception as e:
        print(f"❌ Error obteniendo updates: {e}")
        health.record_error("get_updates", e)
        
    return []


# ══════════════════════════════════════════════════════════════
# HANDLER DE MENSAJES
# ══════════════════════════════════════════════════════════════

_estados = {}
_estados_lock = Lock()
_pendientes = {}

def handle(msg):
    """Manejo de mensajes - SIN CAMBIOS EN LA LÓGICA"""
    try:
        chat_id = str(msg["chat"]["id"])
        username = msg["from"].get("username", "Desconocido")
        text = msg.get("text", "").strip()

        if not text:
            return

        es_admin = (chat_id == ADMIN_CHAT_ID)

        # ── START ──
        if text == "/start":
            send(chat_id,
                 "𓂀 <b>ANUBIS CHK</b>\n\n"
                 "🔐 <b>Comandos:</b>\n"
                 "/login - Iniciar sesión\n"
                 "/registro - Crear cuenta\n"
                 "/mislives - Ver estadísticas\n\n"
                 "Creado por @UsuarioPro")
            return

        # ── REGISTRO ──
        if text == "/registro":
            with _estados_lock:
                _estados[chat_id] = {"paso": "username"}
            send(chat_id, "📝 <b>REGISTRO</b>\n\nIngresa un nombre de usuario:")
            return

        # ── PROCESO DE REGISTRO ──
        with _estados_lock:
            estado = _estados.get(chat_id)

        if estado:
            if estado["paso"] == "username":
                uname = text
                with _estados_lock:
                    _estados[chat_id] = {"paso": "password", "username": uname}
                send(chat_id, "🔐 Ahora ingresa una contraseña:")
                return

            elif estado["paso"] == "password":
                pwd = text
                uname = estado["username"]

                with _estados_lock:
                    _estados[chat_id] = {"paso": "confirmar", "username": uname, "password": pwd}

                send(chat_id,
                     f"✅ <b>CONFIRMA TU REGISTRO</b>\n\n"
                     f"Usuario: <code>{uname}</code>\n"
                     f"Contraseña: <code>{pwd}</code>\n\n"
                     f"¿Es correcto? Responde <b>SI</b> o <b>NO</b>")
                return

            elif estado["paso"] == "confirmar":
                if text.upper() == "SI":
                    uname = estado["username"]
                    pwd = estado["password"]

                    usuarios = obtener_todos_usuarios()
                    for u in usuarios:
                        if u.get("username", "").lower() == uname.lower():
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
# MAIN LOOP MEJORADO
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
    
    # Notificar SOLO SI ESTÁ HABILITADO
    if Config.NOTIFY_RESTARTS:
        try:
            send(ADMIN_CHAT_ID, "🚀 <b>BOT ONLINE</b>")
        except Exception as e:
            print(f"⚠️ No se pudo notificar al admin: {e}")
    
    print("✅ Bot iniciado. Esperando mensajes...")

    offset = 0
    consecutive_errors = 0
    last_successful_update = time.time()
    health_check_counter = 0
    
    while not shutdown_event.is_set():
        try:
            updates = get_updates(offset)
            
            if updates:
                consecutive_errors = 0
                last_successful_update = time.time()
                
                for update in updates:
                    offset = update["update_id"] + 1
                    
                    if "message" in update:
                        try:
                            handle(update["message"])
                        except Exception as e:
                            print(f"❌ Error procesando mensaje: {e}")
                            health.record_error("message_handler", e)
            
            # Health check MUY ESPACIADO
            health_check_counter += 1
            if health_check_counter >= 240:  # Cada 2 minutos (0.5s * 240)
                health_check_counter = 0
                
                if not health.is_healthy():
                    print("⚠️ Sistema no saludable detectado")
                    time.sleep(60)  # Esperar 1 minuto antes de considerar reinicio
                    
                    # Verificar de nuevo después de esperar
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
    
    # Shutdown graceful
    print("🛑 Iniciando shutdown graceful...")
    
    if Config.NOTIFY_RESTARTS:
        try:
            send(ADMIN_CHAT_ID, "⚠️ Bot apagándose...")
        except:
            pass
    
    time.sleep(Config.SHUTDOWN_GRACE_PERIOD)
    print("✅ Shutdown completado")


# ══════════════════════════════════════════════════════════════
# ENTRY POINT — SOLO RESTART SI ES NECESARIO
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    restart_count = 0
    max_restarts = 5  # REDUCIDO de 100 a 5
    last_start = time.time()
    
    while restart_count < max_restarts:
        try:
            print(f"\n{'='*60}")
            print(f"🚀 Iniciando bot (restart #{restart_count})")
            print(f"{'='*60}\n")
            
            main_loop()
            
            # Si fue shutdown intencional, salir
            if shutdown_event.is_set():
                print("✅ Shutdown intencional. Saliendo...")
                break
            
        except Exception as e:
            print(f"\n💀 CRASH CRÍTICO: {e}")
            print(traceback.format_exc())
            
        restart_count += 1
        
        # Evitar restarts muy rápidos
        uptime = time.time() - last_start
        if uptime < 60:  # Si corrió menos de 1 minuto
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
