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
    admin_id = os.environ.get("ADMIN_CHAT_ID", "7448403516")
    creator_username = os.environ.get("CREATOR_USERNAME", "ProChekCc")
    firebase_creds = os.environ.get("FIREBASE_CREDENTIALS")

    # Si hay variables de entorno, usarlas
    if token and firebase_creds:
        try:
            creds_dict = json.loads(firebase_creds)
            return token, str(admin_id), creator_username, creds_dict
        except:
            pass

    # Intentar cargar desde archivos
    try:
        _BASE = os.path.dirname(os.path.abspath(__file__))
        
        # Cargar config.json
        config_file = os.path.join(_BASE, "config.json")
        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
                token = config.get("telegram_token", token)
                admin_id = config.get("admin_chat_id", admin_id)
        
        # Cargar firebase-credentials.json
        cred_file = os.path.join(_BASE, "firebase-credentials.json")
        if os.path.exists(cred_file):
            with open(cred_file, 'r', encoding='utf-8') as f:
                firebase_creds = json.load(f)
        
        if token and firebase_creds:
            return token, str(admin_id), creator_username, firebase_creds
            
    except Exception as e:
        print(f"⚠️ Error cargando config: {e}")
    
    raise RuntimeError("❌ Configuración faltante - verifica TELEGRAM_TOKEN y credenciales de Firebase")


TELEGRAM_TOKEN, ADMIN_CHAT_ID, CREATOR_USERNAME, FIREBASE_CREDS = _cargar_config()

print(f"✅ Config cargada - Admin ID: {ADMIN_CHAT_ID}")
print(f"✅ Creator: @{CREATOR_USERNAME}")

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
            "boot_time": datetime.fromtimestamp(psutil.boot_time()).strftime("%Y-%m-%d %H:%M:%S"),
            "firebase_project": FIREBASE_CREDS.get("project_id", "N/A"),
            "admin_id": ADMIN_CHAT_ID,
            "creator": CREATOR_USERNAME,
            "version": "2.1"
        }
    except:
        return {
            "cpu_percent": 0,
            "memory_percent": 0,
            "disk_percent": 0,
            "boot_time": "N/A",
            "firebase_project": FIREBASE_CREDS.get("project_id", "N/A"),
            "admin_id": ADMIN_CHAT_ID,
            "creator": CREATOR_USERNAME,
            "version": "2.1"
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
            try:
                data = doc.to_dict()
                
                # Asegurarse de que todos los campos existen
                if data:
                    # Campos obligatorios con valores por defecto
                    user_data = {
                        "username": data.get("username", doc.id),
                        "lives_count": data.get("lives_count", 0),
                        "activo": data.get("activo", True),
                        "bloqueado": data.get("bloqueado", False),
                        "chat_id": data.get("chat_id", "N/A"),
                        "created_at": data.get("created_at"),
                        "last_login": data.get("last_login"),
                        "intentos_fallidos": data.get("intentos_fallidos", 0)
                    }
                    users.append(user_data)
            except Exception as e:
                print(f"⚠️ Error procesando usuario {doc.id}: {e}")
                continue
        
        return users
        
    except Exception as e:
        print(f"❌ Error obteniendo usuarios: {e}")
        return []


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
# MODERADORES
# ══════════════════════════════════════════════════════════════

def agregar_moderador(chat_id, username=None):
    """Agregar un moderador"""
    try:
        db = get_db()
        mod_id = str(chat_id)
        
        ref = db.collection("moderadores").document(mod_id)
        ref.set({
            "chat_id": mod_id,
            "username": username or "N/A",
            "agregado_at": firestore.SERVER_TIMESTAMP,
            "activo": True
        })
        
        log_evento("moderador_agregado", {"chat_id": mod_id, "username": username})
        return True
    except Exception as e:
        print(f"❌ Error agregando moderador: {e}")
        return False

def eliminar_moderador(chat_id):
    """Eliminar un moderador"""
    try:
        db = get_db()
        db.collection("moderadores").document(str(chat_id)).delete()
        log_evento("moderador_eliminado", str(chat_id))
        return True
    except:
        return False

def es_moderador(chat_id):
    """Verifica si un chat_id es moderador"""
    try:
        db = get_db()
        doc = db.collection("moderadores").document(str(chat_id)).get()
        if doc.exists:
            data = doc.to_dict()
            return data.get("activo", False)
        return False
    except:
        return False

def obtener_moderadores():
    """Obtiene la lista de moderadores"""
    try:
        db = get_db()
        docs = db.collection("moderadores").where("activo", "==", True).stream()
        
        mods = []
        for doc in docs:
            data = doc.to_dict()
            mods.append(data)
        
        return mods
    except Exception as e:
        print(f"❌ Error obteniendo moderadores: {e}")
        return []

# ══════════════════════════════════════════════════════════════
# GESTIÓN DE LIVES (USUARIOS)
# ══════════════════════════════════════════════════════════════

def agregar_lives(username, cantidad):
    """Agrega lives a un usuario"""
    try:
        db = get_db()
        ref = db.collection("usuarios").document(username.lower())
        doc = ref.get()
        
        if not doc.exists:
            return {"ok": False, "error": "Usuario no encontrado"}
        
        ref.update({
            "lives_count": firestore.Increment(cantidad)
        })
        
        log_evento("lives_agregadas", {"username": username, "cantidad": cantidad})
        return {"ok": True, "mensaje": f"Se agregaron {cantidad} lives a {username}"}
        
    except Exception as e:
        return {"ok": False, "error": str(e)}

def quitar_lives(username, cantidad):
    """Quita lives a un usuario"""
    try:
        db = get_db()
        ref = db.collection("usuarios").document(username.lower())
        doc = ref.get()
        
        if not doc.exists:
            return {"ok": False, "error": "Usuario no encontrado"}
        
        data = doc.to_dict()
        lives_actuales = data.get("lives_count", 0)
        
        if lives_actuales < cantidad:
            return {"ok": False, "error": f"El usuario solo tiene {lives_actuales} lives"}
        
        ref.update({
            "lives_count": firestore.Increment(-cantidad)
        })
        
        log_evento("lives_quitadas", {"username": username, "cantidad": cantidad})
        return {"ok": True, "mensaje": f"Se quitaron {cantidad} lives a {username}"}
        
    except Exception as e:
        return {"ok": False, "error": str(e)}

def establecer_lives(username, cantidad):
    """Establece un número exacto de lives"""
    try:
        db = get_db()
        ref = db.collection("usuarios").document(username.lower())
        doc = ref.get()
        
        if not doc.exists:
            return {"ok": False, "error": "Usuario no encontrado"}
        
        ref.update({
            "lives_count": cantidad
        })
        
        log_evento("lives_establecidas", {"username": username, "cantidad": cantidad})
        return {"ok": True, "mensaje": f"Lives de {username} establecidas a {cantidad}"}
        
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ══════════════════════════════════════════════════════════════
# GESTIÓN DE LIVES/TARJETAS (FIREBASE)
# ══════════════════════════════════════════════════════════════

def obtener_todas_las_tarjetas():
    """
    Obtiene todas las tarjetas de la colección lives/anon/tarjetas
    """
    try:
        db = get_db()
        tarjetas = []
        
        # Navegar a: lives (colección) -> anon (documento) -> tarjetas (sub-colección)
        tarjetas_ref = db.collection('lives').document('anon').collection('tarjetas')
        docs = tarjetas_ref.stream()
        
        for doc in docs:
            tarjeta_data = doc.to_dict()
            tarjeta_data['id'] = doc.id
            tarjetas.append(tarjeta_data)
        
        return {"ok": True, "tarjetas": tarjetas, "total": len(tarjetas)}
        
    except Exception as e:
        print(f"❌ Error obteniendo tarjetas: {e}")
        return {"ok": False, "error": str(e), "tarjetas": [], "total": 0}

def obtener_tarjeta_por_id(tarjeta_id):
    """
    Obtiene una tarjeta específica por su ID
    """
    try:
        db = get_db()
        
        tarjeta_ref = db.collection('lives').document('anon').collection('tarjetas').document(tarjeta_id)
        doc = tarjeta_ref.get()
        
        if not doc.exists:
            return {"ok": False, "error": "Tarjeta no encontrada"}
        
        tarjeta_data = doc.to_dict()
        tarjeta_data['id'] = doc.id
        
        return {"ok": True, "tarjeta": tarjeta_data}
        
    except Exception as e:
        print(f"❌ Error obteniendo tarjeta: {e}")
        return {"ok": False, "error": str(e)}

def agregar_tarjeta(tarjeta_id, datos=None):
    """
    Agrega una nueva tarjeta a Firebase
    """
    try:
        db = get_db()
        
        tarjeta_ref = db.collection('lives').document('anon').collection('tarjetas').document(tarjeta_id)
        
        # Verificar si ya existe
        if tarjeta_ref.get().exists:
            return {"ok": False, "error": "La tarjeta ya existe"}
        
        # Datos por defecto si no se proporcionan
        if datos is None:
            datos = {}
        
        datos_tarjeta = {
            "creada_at": firestore.SERVER_TIMESTAMP,
            "activa": True,
            **datos
        }
        
        tarjeta_ref.set(datos_tarjeta)
        
        log_evento("tarjeta_agregada", tarjeta_id)
        return {"ok": True, "mensaje": f"Tarjeta {tarjeta_id} agregada"}
        
    except Exception as e:
        print(f"❌ Error agregando tarjeta: {e}")
        return {"ok": False, "error": str(e)}

def eliminar_tarjeta(tarjeta_id):
    """
    Elimina una tarjeta de Firebase
    """
    try:
        db = get_db()
        
        tarjeta_ref = db.collection('lives').document('anon').collection('tarjetas').document(tarjeta_id)
        
        if not tarjeta_ref.get().exists:
            return {"ok": False, "error": "Tarjeta no encontrada"}
        
        tarjeta_ref.delete()
        
        log_evento("tarjeta_eliminada", tarjeta_id)
        return {"ok": True, "mensaje": f"Tarjeta {tarjeta_id} eliminada"}
        
    except Exception as e:
        print(f"❌ Error eliminando tarjeta: {e}")
        return {"ok": False, "error": str(e)}

def actualizar_tarjeta(tarjeta_id, datos):
    """
    Actualiza los datos de una tarjeta
    """
    try:
        db = get_db()
        
        tarjeta_ref = db.collection('lives').document('anon').collection('tarjetas').document(tarjeta_id)
        
        if not tarjeta_ref.get().exists:
            return {"ok": False, "error": "Tarjeta no encontrada"}
        
        tarjeta_ref.update(datos)
        
        log_evento("tarjeta_actualizada", {"tarjeta_id": tarjeta_id, "datos": datos})
        return {"ok": True, "mensaje": f"Tarjeta {tarjeta_id} actualizada"}
        
    except Exception as e:
        print(f"❌ Error actualizando tarjeta: {e}")
        return {"ok": False, "error": str(e)}

# ══════════════════════════════════════════════════════════════
# STATS GLOBALES
# ══════════════════════════════════════════════════════════════

def stats_globales():
    try:
        usuarios = obtener_todos_usuarios()

        total = len(usuarios)
        activos = sum(1 for u in usuarios if u.get("activo"))
        inactivos = total - activos
        bloqueados = sum(1 for u in usuarios if u.get("bloqueado"))
        lives = sum(u.get("lives_count", 0) for u in usuarios)

        return {
            "total": total,
            "activos": activos,
            "inactivos": inactivos,
            "bloqueados": bloqueados,
            "lives": lives
        }

    except:
        return {
            "total": 0,
            "activos": 0,
            "inactivos": 0,
            "bloqueados": 0,
            "lives": 0
        }
