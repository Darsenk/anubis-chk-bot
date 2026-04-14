"""
═══════════════════════════════════════════════════════════════
BOT TELEGRAM — ANUBIS CHK (24/7 ACTIVO)
═══════════════════════════════════════════════════════════════
Versión optimizada para Koyeb:
- Puerto correcto (8000)
- Health check HTTP mejorado
- Sin sleep mode
- Notificaciones garantizadas
═══════════════════════════════════════════════════════════════
"""

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
)

API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

_estados = {}
_pendientes = {}


# ══════════════════════════════════════════════════════════════
# SERVIDOR HTTP PARA HEALTH CHECKS
# ══════════════════════════════════════════════════════════════
class HealthCheckHandler(BaseHTTPRequestHandler):
    """Handler HTTP para health checks de Koyeb"""
    
    def do_GET(self):
        """Responde a GET requests de health check"""
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        
        response = {
            "status": "healthy",
            "service": "ANUBIS CHK Bot",
            "bot": "online",
            "timestamp": int(time.time()),
            "uptime": int(time.time() - start_time)
        }
        
        self.wfile.write(json.dumps(response).encode())
    
    def do_HEAD(self):
        """Responde a HEAD requests"""
        self.send_response(200)
        self.end_headers()
    
    def log_message(self, format, *args):
        """Silenciar logs HTTP"""
        pass


def run_http_server():
    """
    Inicia el servidor HTTP en el puerto 8000 (requerido por Koyeb).
    """
    # IMPORTANTE: Usar puerto 8000 para Koyeb
    port = int(os.environ.get('PORT', 8000))
    
    try:
        server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
        print(f"✅ HTTP Server iniciado en puerto {port}")
        print(f"   Health check disponible en: http://0.0.0.0:{port}/")
        server.serve_forever()
    except Exception as e:
        print(f"❌ Error al iniciar servidor HTTP: {e}")
        # Intentar con puerto alternativo
        try:
            port = 8080
            server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
            print(f"✅ HTTP Server iniciado en puerto alternativo {port}")
            server.serve_forever()
        except:
            print(f"❌ No se pudo iniciar servidor HTTP en ningún puerto")


# ══════════════════════════════════════════════════════════════
# FUNCIONES DEL BOT DE TELEGRAM
# ══════════════════════════════════════════════════════════════
def send(chat_id, text, parse_mode="HTML"):
    """Envía mensaje de Telegram con retry automático"""
    max_intentos = 3
    for intento in range(max_intentos):
        try:
            response = requests.post(
                f"{API}/sendMessage",
                data={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": parse_mode,
                },
                timeout=10
            )
            
            if response.status_code == 200:
                return True
            else:
                print(f"⚠️ Error enviando mensaje (intento {intento + 1}/{max_intentos}): {response.status_code}")
                
        except Exception as e:
            print(f"❌ Excepción enviando mensaje (intento {intento + 1}/{max_intentos}): {e}")
        
        if intento < max_intentos - 1:
            time.sleep(1)
    
    return False


def get_updates(offset=0):
    """Obtiene actualizaciones de Telegram con timeout largo"""
    try:
        r = requests.get(
            f"{API}/getUpdates",
            params={
                "offset": offset,
                "timeout": 30,
            },
            timeout=35
        )
        return r.json().get("result", [])
    except Exception as e:
        print(f"⚠️ Error obteniendo updates: {e}")
        return []


def handle(msg):
    """Procesa los mensajes recibidos"""
    chat_id = str(msg["chat"]["id"])
    text = msg.get("text", "").strip()
    username = msg.get("from", {}).get("username", "")
    nombre = msg.get("from", {}).get("first_name", "Usuario")
    es_admin = (chat_id == str(ADMIN_CHAT_ID))

    # ── /start ────────────────────────────────────────────────
    if text == "/start":
        send(chat_id,
             f"𓂀 <b>ANUBIS CHK</b>\n"
             f"━━━━━━━━━━━━━━━━━━\n"
             f"Bienvenido, <b>{nombre}</b>\n\n"
             f"📋 Comandos disponibles:\n"
             f"  /registro — Solicitar acceso\n"
             f"  /mislives — Ver tus lives\n"
             + (f"  /usuarios — Ver todos los usuarios\n"
                f"  /adduser — Agregar usuario manualmente\n"
                f"  /ping — Verificar estado del bot\n"
                f"  /status — Estado del servidor\n"
                if es_admin else ""))
        return

    # ── /ping (solo admin) ────────────────────────────────────
    if text == "/ping" and es_admin:
        uptime = int(time.time() - start_time)
        send(chat_id,
             f"✅ <b>BOT ACTIVO</b>\n"
             f"━━━━━━━━━━━━━━━━━━\n"
             f"🤖 Operando correctamente\n"
             f"⏰ {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
             f"🔄 Uptime: {uptime//3600}h {(uptime%3600)//60}m")
        return

    # ── /status (solo admin) ──────────────────────────────────
    if text == "/status" and es_admin:
        usuarios = obtener_todos_usuarios()
        uptime = int(time.time() - start_time)
        send(chat_id,
             f"📊 <b>ESTADO DEL SISTEMA</b>\n"
             f"━━━━━━━━━━━━━━━━━━\n"
             f"🤖 Bot: ONLINE\n"
             f"🌐 HTTP Server: ACTIVE\n"
             f"👥 Usuarios: {len(usuarios)}\n"
             f"⏰ Uptime: {uptime//3600}h {(uptime%3600)//60}m\n"
             f"📅 {time.strftime('%Y-%m-%d %H:%M:%S')}")
        return

    # ── /registro ─────────────────────────────────────────────
    if text == "/registro":
        _estados[chat_id] = {"step": "esperando_usuario"}
        send(chat_id,
             "📝 <b>REGISTRO DE ACCESO</b>\n"
             "━━━━━━━━━━━━━━━━━━\n"
             "Escribe el <b>usuario</b> que quieres usar:")
        return

    # ── /mislives ─────────────────────────────────────────────
    if text == "/mislives":
        usuarios = obtener_todos_usuarios()
        for u in usuarios:
            if str(u.get("chat_id", "")) == chat_id:
                send(chat_id,
                     f"📊 <b>TUS ESTADÍSTICAS</b>\n"
                     f"━━━━━━━━━━━━━━━━━━\n"
                     f"👤 Usuario: <b>{u['username']}</b>\n"
                     f"✅ Lives encontradas: <b>{u.get('lives_count', 0)}</b>")
                return
        send(chat_id, "❌ No tienes cuenta registrada. Usa /registro")
        return

    # ── /usuarios (solo admin) ────────────────────────────────
    if text == "/usuarios" and es_admin:
        usuarios = obtener_todos_usuarios()
        if not usuarios:
            send(chat_id, "📭 No hay usuarios registrados.")
            return
        
        lines = ["👥 <b>USUARIOS ACTIVOS</b>\n━━━━━━━━━━━━━━━━━━"]
        for u in usuarios:
            lines.append(
                f"👤 <b>{u['username']}</b>\n"
                f"   💬 TG: @{u.get('telegram_user', '—')}\n"
                f"   ✅ Lives: {u.get('lives_count', 0)}\n"
                f"   🆔 Chat ID: {u.get('chat_id', '—')}"
            )
        send(chat_id, "\n\n".join(lines))
        return

    # ── /adduser (admin agrega usuario directamente) ──────────
    if text.startswith("/adduser") and es_admin:
        partes = text.split()
        if len(partes) < 4:
            send(chat_id,
                 "⚠️ Uso correcto:\n"
                 "<code>/adduser username contraseña chat_id</code>")
            return
        
        _, uname, pwd, cid = partes[0], partes[1], partes[2], partes[3]
        resultado = registrar_usuario(uname, pwd, cid)
        
        if resultado["ok"]:
            send(chat_id,
                 f"✅ Usuario <b>{uname}</b> creado correctamente.\n"
                 f"🔑 Contraseña: <code>{pwd}</code>\n"
                 f"🆔 Chat ID: <code>{cid}</code>")
            
            send(cid,
                 f"✅ <b>Acceso aprobado</b>\n"
                 f"━━━━━━━━━━━━━━━━━━\n"
                 f"👤 Usuario: <code>{uname}</code>\n"
                 f"🔑 Contraseña: <code>{pwd}</code>\n\n"
                 f"Ya puedes iniciar sesión en ANUBIS CHK.\n"
                 f"🤖 @anubischekbot")
        else:
            send(chat_id, f"❌ Error: {resultado['error']}")
        return

    # ── Flujo de registro paso a paso ─────────────────────────
    estado = _estados.get(chat_id, {})
    step = estado.get("step", "")

    if step == "esperando_usuario":
        if len(text) < 3 or " " in text:
            send(chat_id, "⚠️ Usuario inválido. Sin espacios, mínimo 3 caracteres.")
            return
        _estados[chat_id] = {"step": "esperando_password", "data": {"username": text}}
        send(chat_id, f"✅ Usuario: <b>{text}</b>\n\nAhora escribe tu <b>contraseña</b>:")
        return

    if step == "esperando_password":
        if len(text) < 4:
            send(chat_id, "⚠️ Contraseña muy corta. Mínimo 4 caracteres.")
            return
        uname = estado["data"]["username"]
        _estados[chat_id] = {"step": "confirmando", "data": {"username": uname, "password": text}}
        send(chat_id,
             f"📋 <b>Confirma tus datos:</b>\n"
             f"━━━━━━━━━━━━━━━━━━\n"
             f"👤 Usuario: <b>{uname}</b>\n"
             f"🔑 Contraseña: <code>{text}</code>\n\n"
             f"Responde <b>SI</b> para confirmar o <b>NO</b> para cancelar.")
        return

    if step == "confirmando":
        if text.upper() == "SI":
            data = estado["data"]
            uname = data["username"]
            pwd = data["password"]

            from firebase_manager import get_db
            db = get_db()
            ref = db.collection("usuarios").document(uname.lower())
            doc = ref.get()

            if doc.exists:
                send(chat_id, "❌ Ese usuario ya existe. Usa otro nombre.")
                del _estados[chat_id]
                return

            _pendientes[chat_id] = {
                "username": uname,
                "password": pwd,
                "chat_id": chat_id,
                "telegram_user": username,
                "nombre": nombre,
            }
            del _estados[chat_id]

            send(chat_id,
                 "⏳ <b>Solicitud enviada al admin.</b>\n"
                 "Recibirás tu acceso cuando sea aprobada.")

            mensaje_admin = (
                f"🔔 <b>NUEVA SOLICITUD DE ACCESO</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"👤 Nombre: {nombre}\n"
                f"📱 Telegram: @{username}\n"
                f"🆔 Chat ID: <code>{chat_id}</code>\n"
                f"🔑 Usuario: <b>{uname}</b>\n"
                f"🔒 Pass: <code>{pwd}</code>\n\n"
                f"Para aprobar:\n"
                f"<code>/adduser {uname} {pwd} {chat_id}</code>"
            )
            
            enviado = send(ADMIN_CHAT_ID, mensaje_admin)
            if not enviado:
                print(f"❌ CRÍTICO: No se pudo notificar al admin sobre solicitud de {uname}")

        elif text.upper() == "NO":
            del _estados[chat_id]
            send(chat_id, "❌ Registro cancelado.")
        else:
            send(chat_id, "Responde <b>SI</b> o <b>NO</b>.")
        return


# Variable global para tracking de uptime
start_time = time.time()


def main():
    """Función principal del bot"""
    global start_time
    start_time = time.time()
    
    print("=" * 60)
    print("🤖 ANUBIS CHK Bot iniciando...")
    print("=" * 60)
    print(f"👑 Admin Chat ID: {ADMIN_CHAT_ID}")
    print(f"🔑 Token: {TELEGRAM_TOKEN[:20]}...")
    print(f"🌐 Puerto HTTP: {os.environ.get('PORT', 8000)}")
    print("=" * 60)
    
    # Iniciar servidor HTTP en thread separado
    http_thread = Thread(target=run_http_server, daemon=True)
    http_thread.start()
    print("✅ Thread HTTP iniciado")
    
    time.sleep(2)
    
    # Notificar al admin
    send(ADMIN_CHAT_ID,
         f"✅ <b>BOT INICIADO</b>\n"
         f"━━━━━━━━━━━━━━━━━━\n"
         f"🤖 ANUBIS CHK está online\n"
         f"⏰ {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    print("✅ Bot listo - esperando mensajes...")
    print("=" * 60)
    
    offset = 0
    errores_consecutivos = 0
    max_errores = 10
    
    while True:
        try:
            updates = get_updates(offset)
            
            if updates:
                errores_consecutivos = 0
            
            for upd in updates:
                offset = upd["update_id"] + 1
                msg = upd.get("message")
                
                if msg and "text" in msg:
                    try:
                        handle(msg)
                    except Exception as e:
                        print(f"❌ Error procesando mensaje: {e}")
                        import traceback
                        traceback.print_exc()
            
            time.sleep(1)
            
        except KeyboardInterrupt:
            print("\n⚠️ Bot detenido por usuario")
            send(ADMIN_CHAT_ID, "⚠️ Bot detenido manualmente")
            break
            
        except Exception as e:
            errores_consecutivos += 1
            print(f"❌ Error en loop principal ({errores_consecutivos}/{max_errores}): {e}")
            
            if errores_consecutivos >= max_errores:
                print("❌ Demasiados errores consecutivos. Deteniendo bot.")
                send(ADMIN_CHAT_ID,
                     f"❌ <b>BOT DETENIDO</b>\n"
                     f"Demasiados errores consecutivos.\n"
                     f"Último error: {str(e)[:100]}")
                break
            
            time.sleep(5)


if __name__ == "__main__":
    main()
