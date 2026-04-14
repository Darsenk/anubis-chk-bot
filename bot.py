"""
═══════════════════════════════════════════════════════════════
BOT TELEGRAM — ANUBIS CHK
═══════════════════════════════════════════════════════════════
Comandos:
  /start         - Bienvenida
  /registro      - Registrarse (el admin le da usuario+pass)
  /mislives      - Ver cuántas lives lleva
  /usuarios      - (solo admin) Ver todos los usuarios
═══════════════════════════════════════════════════════════════
Ejecutar: python bot.py
"""

import os
import sys
import time
import requests

# Agregar carpeta padre al path para importar firebase_manager
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

# ── Estados de conversación ───────────────────────────────────
# {chat_id: {"step": "...", "data": {...}}}
_estados = {}

# ── Sesiones pendientes de aprobación (admin crea usuarios) ──
# {chat_id_usuario: {"username": ..., "password": ...}}
_pendientes = {}


def send(chat_id, text, parse_mode="HTML"):
    try:
        requests.post(f"{API}/sendMessage", data={
            "chat_id":    chat_id,
            "text":       text,
            "parse_mode": parse_mode,
        }, timeout=10)
    except Exception:
        pass


def get_updates(offset=0):
    try:
        r = requests.get(f"{API}/getUpdates", params={
            "offset":  offset,
            "timeout": 30,
        }, timeout=35)
        return r.json().get("result", [])
    except Exception:
        return []


def handle(msg):
    chat_id  = str(msg["chat"]["id"])
    text     = msg.get("text", "").strip()
    username = msg.get("from", {}).get("username", "")
    nombre   = msg.get("from", {}).get("first_name", "Usuario")
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
                if es_admin else ""))
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
    # Uso: /adduser username password chat_id
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
                 f"Ya puedes iniciar sesión en ANUBIS CHK.")
        else:
            send(chat_id, f"❌ Error: {resultado['error']}")
        return

    # ── Flujo de registro paso a paso ─────────────────────────
    estado = _estados.get(chat_id, {})
    step   = estado.get("step", "")

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
            data  = estado["data"]
            uname = data["username"]
            pwd   = data["password"]

            # Verificar si ya existe
            from firebase_manager import get_db
            db  = get_db()
            ref = db.collection("usuarios").document(uname.lower())
            doc = ref.get()

            if doc.exists:
                send(chat_id, "❌ Ese usuario ya existe. Usa otro nombre.")
                del _estados[chat_id]
                return

            # Guardar solicitud pendiente
            _pendientes[chat_id] = {
                "username":      uname,
                "password":      pwd,
                "chat_id":       chat_id,
                "telegram_user": username,
                "nombre":        nombre,
            }
            del _estados[chat_id]

            send(chat_id,
                 "⏳ <b>Solicitud enviada al admin.</b>\n"
                 "Recibirás tu acceso cuando sea aprobada.")

            # Notificar al admin
            send(ADMIN_CHAT_ID,
                 f"🔔 <b>NUEVA SOLICITUD DE ACCESO</b>\n"
                 f"━━━━━━━━━━━━━━━━━━\n"
                 f"👤 Nombre: {nombre}\n"
                 f"📱 Telegram: @{username}\n"
                 f"🆔 Chat ID: <code>{chat_id}</code>\n"
                 f"🔑 Usuario: <b>{uname}</b>\n"
                 f"🔒 Pass: <code>{pwd}</code>\n\n"
                 f"Para aprobar:\n"
                 f"<code>/adduser {uname} {pwd} {chat_id}</code>")

        elif text.upper() == "NO":
            del _estados[chat_id]
            send(chat_id, "❌ Registro cancelado.")
        else:
            send(chat_id, "Responde <b>SI</b> o <b>NO</b>.")
        return


def main():
    print("🤖 Bot ANUBIS CHK iniciado...")
    print(f"👑 Admin ID: {ADMIN_CHAT_ID}")
    offset = 0
    while True:
        updates = get_updates(offset)
        for upd in updates:
            offset = upd["update_id"] + 1
            msg    = upd.get("message")
            if msg and "text" in msg:
                try:
                    handle(msg)
                except Exception as e:
                    print(f"Error procesando mensaje: {e}")
        time.sleep(1)


if __name__ == "__main__":
    main()
