"""
═══════════════════════════════════════════════════════════════
FIREBASE MANAGER — ANUBIS CHK (COMPLETO)
═══════════════════════════════════════════════════════════════
"""

import os
import json
import firebase_admin
from firebase_admin import credentials, firestore

# ══════════════════════════════════════════════════════════════
# CONFIG
# ══════════════════════════════════════════════════════════════

def _cargar_config():
    token = os.environ.get("TELEGRAM_TOKEN")
    admin_id = os.environ.get("ADMIN_CHAT_ID")
    firebase_creds_json = os.environ.get("FIREBASE_CREDENTIALS")

    if token and admin_id and firebase_creds_json:
        try:
            creds_dict = json.loads(firebase_creds_json)
        except json.JSONDecodeError:
            raise RuntimeError("FIREBASE_CREDENTIALS no es JSON válido")
        return token, str(admin_id), creds_dict

    # fallback local
    try:
        import config
        token = token or getattr(config, "TELEGRAM_TOKEN", None)
        admin_id = admin_id or str(getattr(config, "ADMIN_CHAT_ID", ""))
        creds_dict = getattr(config, "FIREBASE_CREDENTIALS", None)

        if not token or not admin_id or not creds_dict:
            raise RuntimeError("Faltan datos en config.py")

        return token, str(admin_id), creds_dict

    except ImportError:
        raise RuntimeError("No hay config.py ni variables de entorno")


TELEGRAM_TOKEN, ADMIN_CHAT_ID, _FIREBASE_CREDENTIALS = _cargar_config()


# ══════════════════════════════════════════════════════════════
# FIREBASE INIT (ANTI-DUPLICATE)
# ══════════════════════════════════════════════════════════════

_db = None

def get_db():
    global _db

    if _db:
        return _db

    try:
        if not firebase_admin._apps:
            cred = credentials.Certificate(_FIREBASE_CREDENTIALS)
            firebase_admin.initialize_app(cred)
            print("✅ Firebase conectado")

        _db = firestore.client()
        return _db

    except Exception as e:
        print(f"❌ Error Firebase init: {e}")
        raise


# ══════════════════════════════════════════════════════════════
# USUARIOS
# ══════════════════════════════════════════════════════════════

def registrar_usuario(username, password, chat_id):
    try:
        db = get_db()
        doc_id = username.lower().strip()

        ref = db.collection("usuarios").document(doc_id)

        if ref.get().exists:
            return {"ok": False, "error": "Usuario ya existe"}

        ref.set({
            "username": username,
            "password": password,
            "chat_id": str(chat_id),
            "lives_count": 0,
            "telegram_user": "",
            "activo": True,
            "created_at": firestore.SERVER_TIMESTAMP
        })

        return {"ok": True}

    except Exception as e:
        print(f"❌ registrar_usuario: {e}")
        return {"ok": False, "error": str(e)}


def verificar_login(username, password):
    try:
        db = get_db()
        doc_id = username.lower().strip()

        doc = db.collection("usuarios").document(doc_id).get()

        if not doc.exists:
            return {"ok": False, "error": "No existe"}

        data = doc.to_dict()

        if data["password"] != password:
            return {"ok": False, "error": "Contraseña incorrecta"}

        if not data.get("activo", True):
            return {"ok": False, "error": "Usuario desactivado"}

        return {"ok": True, "data": data}

    except Exception as e:
        print(f"❌ verificar_login: {e}")
        return {"ok": False, "error": str(e)}


def obtener_todos_usuarios():
    try:
        db = get_db()
        usuarios = []

        for doc in db.collection("usuarios").stream():
            data = doc.to_dict()
            data["_id"] = doc.id
            usuarios.append(data)

        return usuarios

    except Exception as e:
        print(f"❌ obtener usuarios: {e}")
        return []


# ══════════════════════════════════════════════════════════════
# EXTRA (IMPORTANTE PARA TU BOT)
# ══════════════════════════════════════════════════════════════

def actualizar_lives(username, cantidad=1):
    try:
        db = get_db()
        doc_id = username.lower().strip()

        ref = db.collection("usuarios").document(doc_id)

        ref.update({
            "lives_count": firestore.Increment(cantidad)
        })

        return True

    except Exception as e:
        print(f"❌ actualizar_lives: {e}")
        return False


def desactivar_usuario(username):
    try:
        db = get_db()
        db.collection("usuarios").document(username.lower()).update({
            "activo": False
        })
        return True
    except:
        return False


def activar_usuario(username):
    try:
        db = get_db()
        db.collection("usuarios").document(username.lower()).update({
            "activo": True
        })
        return True
    except:
        return False


def eliminar_usuario(username):
    try:
        db = get_db()
        db.collection("usuarios").document(username.lower()).delete()
        return True
    except:
        return False
