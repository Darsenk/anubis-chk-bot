"""
═══════════════════════════════════════════════════════════════
FIREBASE MANAGER — ANUBIS CHK (PRO MAX)
═══════════════════════════════════════════════════════════════
"""

import os
import json
import time
import hashlib
import random
import string
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime

# ══════════════════════════════════════════════════════════════
# CONFIG
# ══════════════════════════════════════════════════════════════

def _cargar_config():
    token = os.environ.get("TELEGRAM_TOKEN")
    admin_id = os.environ.get("ADMIN_CHAT_ID")
    creator_username = os.environ.get("CREATOR_USERNAME", "@AnubisCHK")
    firebase_creds = os.environ.get("FIREBASE_CREDENTIALS")

    if token and admin_id and firebase_creds:
        return token, str(admin_id), creator_username, json.loads(firebase_creds)

    try:
        import config
        return (
            getattr(config, "TELEGRAM_TOKEN"),
            str(getattr(config, "ADMIN_CHAT_ID")),
            getattr(config, "CREATOR_USERNAME", "@AnubisCHK"),
            getattr(config, "FIREBASE_CREDENTIALS")
        )
    except:
        raise RuntimeError("❌ Configuración faltante")


TELEGRAM_TOKEN, ADMIN_CHAT_ID, CREATOR_USERNAME, FIREBASE_CREDS = _cargar_config()

# ══════════════════════════════════════════════════════════════
# FIREBASE INIT
# ══════════════════════════════════════════════════════════════

_db = None

def get_db():
    global _db
    if _db:
        return _db

    if not firebase_admin._apps:
        cred = credentials.Certificate(FIREBASE_CREDS)
        firebase_admin.initialize_app(cred)

    _db = firestore.client()
    print("✅ Firebase listo")
    return _db

# ══════════════════════════════════════════════════════════════
# CACHE + RATE LIMIT
# ══════════════════════════════════════════════════════════════

_cache = {}
_rate_limit = {}

def rate_limit(chat_id, limite=5, ventana=10):
    ahora = time.time()

    if chat_id not in _rate_limit:
        _rate_limit[chat_id] = []

    _rate_limit[chat_id] = [
        t for t in _rate_limit[chat_id]
        if ahora - t < ventana
    ]

    if len(_rate_limit[chat_id]) >= limite:
        return False

    _rate_limit[chat_id].append(ahora)
    return True

# ══════════════════════════════════════════════════════════════
# UTILIDADES
# ══════════════════════════════════════════════════════════════

def _hash(password):
    return hashlib.sha256(password.encode()).hexdigest()

def _generar_password(longitud=8):
    """Genera una contraseña aleatoria"""
    caracteres = string.ascii_letters + string.digits
    return ''.join(random.choice(caracteres) for _ in range(longitud))

def log_evento(tipo, data):
    try:
        db = get_db()
        db.collection("logs").add({
            "tipo": tipo,
            "data": data,
            "timestamp": firestore.SERVER_TIMESTAMP
        })
    except:
        pass

def get_system_info():
    """Obtiene información del sistema"""
    try:
        import psutil
        
        return {
            "cpu_percent": psutil.cpu_percent(interval=1),
            "memory_percent": psutil.virtual_memory().percent,
            "disk_percent": psutil.disk_usage('/').percent,
            "boot_time": datetime.fromtimestamp(psutil.boot_time()).strftime("%Y-%m-%d %H:%M:%S")
        }
    except:
        return {
            "cpu_percent": 0,
            "memory_percent": 0,
            "disk_percent": 0,
            "boot_time": "N/A"
        }

# ══════════════════════════════════════════════════════════════
# USUARIOS
# ══════════════════════════════════════════════════════════════

def registrar_usuario(username, password, chat_id):
    try:
        db = get_db()
        doc_id = username.lower().strip()

        ref = db.collection("usuarios").document(doc_id)

        if ref.get().exists:
            return {"ok": False, "error": "Ya existe"}

        ref.set({
            "username": username,
            "password_hash": _hash(password),
            "chat_id": str(chat_id),
            "lives_count": 0,
            "activo": True,
            "bloqueado": False,
            "intentos_fallidos": 0,
            "created_at": firestore.SERVER_TIMESTAMP,
            "last_login": None
        })

        log_evento("registro", username)

        return {"ok": True}

    except Exception as e:
        return {"ok": False, "error": str(e)}

# ══════════════════════════════════════════════════════════════
# LOGIN
# ══════════════════════════════════════════════════════════════

def verificar_login(username, password):
    try:
        db = get_db()
        doc_id = username.lower().strip()

        ref = db.collection("usuarios").document(doc_id)
        doc = ref.get()

        if not doc.exists:
            return {"ok": False, "error": "No existe"}

        data = doc.to_dict()

        if data.get("bloqueado"):
            return {"ok": False, "error": "Usuario bloqueado"}

        if data.get("password_hash") != _hash(password):
            intentos = data.get("intentos_fallidos", 0) + 1

            ref.update({"intentos_fallidos": intentos})

            if intentos >= 5:
                ref.update({"bloqueado": True})

            return {"ok": False, "error": "Contraseña incorrecta"}

        # login correcto
        ref.update({
            "intentos_fallidos": 0,
            "last_login": firestore.SERVER_TIMESTAMP
        })

        log_evento("login", username)

        return {"ok": True, "data": data}

    except Exception as e:
        return {"ok": False, "error": str(e)}

# ══════════════════════════════════════════════════════════════
# CONSULTAS
# ══════════════════════════════════════════════════════════════
def get_usuario_por_chat(chat_id):
    try:
        db = get_db()
        docs = db.collection("usuarios").where("chat_id", "==", str(chat_id)).stream()

        for doc in docs:
            return doc.to_dict()

        return None
    except:
        return None

def obtener_usuario(username):
    if username in _cache:
        return _cache[username]

    try:
        db = get_db()
        doc = db.collection("usuarios").document(username.lower()).get()

        if not doc.exists:
            return None

        data = doc.to_dict()
        _cache[username] = data
        return data

    except:
        return None


def obtener_todos_usuarios():
    """Obtener todos los usuarios con verificación de datos"""
    try:
        db = get_db()
        users = []
        
        # Obtener todos los documentos de la colección usuarios
        docs = db.collection("usuarios").stream()
        
        for doc in docs:
            data = doc.to_dict()
            
            # Verificar que el documento tenga los campos necesarios
            if data:
                # Asegurarse de que el ID del documento también se incluya
                data['doc_id'] = doc.id
                
                # Convertir chat_id a string si es necesario
                if 'chat_id' in data and data['chat_id']:
                    data['chat_id'] = str(data['chat_id'])
                
                # Asegurar que username exista
                if 'username' not in data:
                    data['username'] = doc.id
                
                users.append(data)
                print(f"✅ Usuario encontrado: {data.get('username', 'N/A')}")
        
        print(f"📊 Total de usuarios encontrados: {len(users)}")
        return users
        
    except Exception as e:
        print(f"❌ Error obteniendo usuarios: {e}")
        import traceback
        traceback.print_exc()
        return []

# ══════════════════════════════════════════════════════════════
# STATS
# ══════════════════════════════════════════════════════════════

def actualizar_lives(username, cantidad=1):
    try:
        db = get_db()
        db.collection("usuarios").document(username.lower()).update({
            "lives_count": firestore.Increment(cantidad)
        })

        log_evento("lives_update", username)
        return True
    except:
        return False

# ══════════════════════════════════════════════════════════════
# ADMIN
# ══════════════════════════════════════════════════════════════

def bloquear_usuario(username):
    try:
        db = get_db()
        db.collection("usuarios").document(username.lower()).update({
            "bloqueado": True
        })
        log_evento("usuario_bloqueado", username)
        return True
    except:
        return False


def desbloquear_usuario(username):
    try:
        db = get_db()
        db.collection("usuarios").document(username.lower()).update({
            "bloqueado": False,
            "intentos_fallidos": 0
        })
        log_evento("usuario_desbloqueado", username)
        return True
    except:
        return False


def activar_usuario(username):
    try:
        db = get_db()
        db.collection("usuarios").document(username.lower()).update({
            "activo": True
        })
        log_evento("usuario_activado", username)
        return True
    except:
        return False


def desactivar_usuario(username):
    try:
        db = get_db()
        db.collection("usuarios").document(username.lower()).update({
            "activo": False
        })
        log_evento("usuario_desactivado", username)
        return True
    except:
        return False


def eliminar_usuario(username):
    try:
        db = get_db()
        db.collection("usuarios").document(username.lower()).delete()
        log_evento("usuario_eliminado", username)
        return True
    except:
        return False


def cambiar_password(username, nueva_password):
    """Cambia la contraseña de un usuario"""
    try:
        db = get_db()
        doc_id = username.lower().strip()
        
        ref = db.collection("usuarios").document(doc_id)
        doc = ref.get()
        
        if not doc.exists:
            return False
        
        ref.update({
            "password_hash": _hash(nueva_password),
            "intentos_fallidos": 0,
            "bloqueado": False
        })
        
        log_evento("password_changed", username)
        return True
        
    except Exception as e:
        print(f"❌ Error cambiando contraseña: {e}")
        return False

# ══════════════════════════════════════════════════════════════
# LOGS
# ══════════════════════════════════════════════════════════════

def obtener_logs_recientes(limite=20):
    """Obtiene los logs más recientes"""
    try:
        db = get_db()
        
        docs = db.collection("logs") \
            .order_by("timestamp", direction=firestore.Query.DESCENDING) \
            .limit(limite) \
            .stream()
        
        logs = []
        for doc in docs:
            data = doc.to_dict()
            
            # Formatear timestamp si existe
            if 'timestamp' in data and data['timestamp']:
                try:
                    ts = data['timestamp']
                    data['timestamp_formatted'] = ts.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    data['timestamp_formatted'] = "N/A"
            
            logs.append(data)
        
        return logs
        
    except Exception as e:
        print(f"❌ Error obteniendo logs: {e}")
        return []

# ══════════════════════════════════════════════════════════════
# STATS GLOBALES
# ══════════════════════════════════════════════════════════════

def stats_globales():
    try:
        usuarios = obtener_todos_usuarios()

        total = len(usuarios)
        activos = sum(1 for u in usuarios if u.get("activo"))
        bloqueados = sum(1 for u in usuarios if u.get("bloqueado"))
        lives = sum(u.get("lives_count", 0) for u in usuarios)

        return {
            "total": total,
            "activos": activos,
            "bloqueados": bloqueados,
            "lives": lives
        }

    except:
        return {
            "total": 0,
            "activos": 0,
            "bloqueados": 0,
            "lives": 0
        }
