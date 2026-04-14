#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════
TEST & DIAGNÓSTICO — ANUBIS CHK
Verifica configuración y funcionalidad del bot
═══════════════════════════════════════════════════════════════
"""

import os
import sys
import json
import time
import requests

def print_header(text):
    print("\n" + "=" * 60)
    print(f"  {text}")
    print("=" * 60)

def test_env_vars():
    """Verificar variables de entorno"""
    print_header("🔍 VERIFICANDO VARIABLES DE ENTORNO")
    
    required = {
        "TELEGRAM_TOKEN": False,
        "ADMIN_CHAT_ID": False,
        "FIREBASE_CREDENTIALS": False
    }
    
    for var in required:
        value = os.environ.get(var)
        required[var] = bool(value)
        
        if value:
            if var == "TELEGRAM_TOKEN":
                display = value[:10] + "..." + value[-5:]
            elif var == "FIREBASE_CREDENTIALS":
                try:
                    creds = json.loads(value)
                    display = f"JSON válido ({len(creds)} campos)"
                except:
                    display = "⚠️ JSON inválido"
            else:
                display = value
            
            print(f"  ✅ {var}: {display}")
        else:
            print(f"  ❌ {var}: No configurado")
    
    all_ok = all(required.values())
    
    if all_ok:
        print("\n✅ Todas las variables están configuradas")
    else:
        print("\n❌ Faltan variables de entorno requeridas")
    
    return all_ok

def test_telegram_connection():
    """Verificar conexión con Telegram"""
    print_header("🔌 VERIFICANDO CONEXIÓN CON TELEGRAM")
    
    token = os.environ.get("TELEGRAM_TOKEN")
    if not token:
        print("❌ TELEGRAM_TOKEN no configurado")
        return False
    
    try:
        api_url = f"https://api.telegram.org/bot{token}/getMe"
        response = requests.get(api_url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if data.get("ok"):
                bot_info = data.get("result", {})
                print(f"  ✅ Conectado exitosamente")
                print(f"  👤 Bot: @{bot_info.get('username')}")
                print(f"  🆔 ID: {bot_info.get('id')}")
                print(f"  📝 Nombre: {bot_info.get('first_name')}")
                return True
        
        print(f"❌ Error de API: {response.status_code}")
        return False
        
    except requests.exceptions.Timeout:
        print("❌ Timeout al conectar con Telegram")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_firebase():
    """Verificar conexión con Firebase"""
    print_header("🔥 VERIFICANDO FIREBASE")
    
    try:
        from firebase_manager import get_db
        
        db = get_db()
        
        # Test de lectura
        test_ref = db.collection("usuarios").limit(1)
        docs = list(test_ref.stream())
        
        print(f"  ✅ Conexión exitosa")
        print(f"  📊 Usuarios en DB: {len(docs)}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_http_server():
    """Verificar que el puerto está disponible"""
    print_header("🌐 VERIFICANDO PUERTO HTTP")
    
    port = int(os.environ.get("PORT", 8000))
    
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        result = s.connect_ex(('localhost', port))
        s.close()
        
        if result == 0:
            print(f"  ⚠️ Puerto {port} ya está en uso")
            return False
        else:
            print(f"  ✅ Puerto {port} disponible")
            return True
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def simulate_load():
    """Simular carga básica"""
    print_header("⚡ PRUEBA DE CARGA BÁSICA")
    
    from firebase_manager import obtener_todos_usuarios
    
    try:
        print("  Obteniendo usuarios...")
        start = time.time()
        usuarios = obtener_todos_usuarios()
        elapsed = time.time() - start
        
        print(f"  ✅ {len(usuarios)} usuarios obtenidos en {elapsed:.2f}s")
        
        if elapsed > 5:
            print(f"  ⚠️ Respuesta lenta (>{elapsed:.2f}s)")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def run_all_tests():
    """Ejecutar todos los tests"""
    print("\n")
    print("╔" + "═" * 58 + "╗")
    print("║" + " " * 15 + "ANUBIS CHK — DIAGNÓSTICO" + " " * 19 + "║")
    print("╚" + "═" * 58 + "╝")
    
    results = {
        "Variables de Entorno": test_env_vars(),
        "Conexión Telegram": test_telegram_connection(),
        "Firebase": test_firebase(),
        "Puerto HTTP": test_http_server(),
        "Prueba de Carga": simulate_load()
    }
    
    print_header("📋 RESUMEN")
    
    for test, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status} - {test}")
    
    all_pass = all(results.values())
    
    print("\n" + "=" * 60)
    if all_pass:
        print("  ✅ TODOS LOS TESTS PASARON")
        print("  🚀 El bot está listo para ejecutarse")
    else:
        print("  ❌ ALGUNOS TESTS FALLARON")
        print("  ⚠️ Revisa los errores antes de ejecutar el bot")
    print("=" * 60 + "\n")
    
    return all_pass

if __name__ == "__main__":
    try:
        success = run_all_tests()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️ Test interrumpido por el usuario")
        sys.exit(1)
    except Exception as e:
        print(f"\n💀 Error crítico: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
