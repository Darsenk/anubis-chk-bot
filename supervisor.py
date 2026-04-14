#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════
SUPERVISOR DE PROCESOS — ANUBIS CHK
Monitorea y reinicia el bot automáticamente
═══════════════════════════════════════════════════════════════
"""

import os
import sys
import time
import subprocess
import signal
from datetime import datetime

class BotSupervisor:
    def __init__(self):
        self.process = None
        self.restart_count = 0
        self.start_time = time.time()
        self.running = True
        
    def log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {message}")
        
    def start_bot(self):
        """Iniciar el proceso del bot"""
        self.log("🚀 Iniciando bot...")
        
        try:
            self.process = subprocess.Popen(
                [sys.executable, "bot.py"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )
            
            self.log(f"✅ Bot iniciado con PID {self.process.pid}")
            return True
            
        except Exception as e:
            self.log(f"❌ Error al iniciar bot: {e}")
            return False
    
    def monitor_output(self):
        """Monitorear salida del bot"""
        if not self.process:
            return
            
        try:
            for line in iter(self.process.stdout.readline, ''):
                if line:
                    print(line.rstrip())
        except:
            pass
    
    def is_alive(self):
        """Verificar si el bot está corriendo"""
        if not self.process:
            return False
        return self.process.poll() is None
    
    def stop_bot(self):
        """Detener el bot gracefully"""
        if not self.process:
            return
            
        self.log("🛑 Deteniendo bot...")
        
        try:
            # Intentar shutdown graceful
            self.process.send_signal(signal.SIGTERM)
            
            # Esperar hasta 10 segundos
            for _ in range(10):
                if self.process.poll() is not None:
                    break
                time.sleep(1)
            
            # Si todavía está vivo, forzar
            if self.process.poll() is None:
                self.log("⚠️ Forzando cierre...")
                self.process.kill()
                
            self.log("✅ Bot detenido")
            
        except Exception as e:
            self.log(f"❌ Error al detener bot: {e}")
    
    def run(self):
        """Loop principal del supervisor"""
        
        # Manejar señales
        def signal_handler(signum, frame):
            self.log(f"🛑 Señal {signum} recibida")
            self.running = False
        
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
        
        self.log("=" * 60)
        self.log("BOT SUPERVISOR INICIADO")
        self.log("=" * 60)
        
        while self.running:
            # Si el bot no está corriendo, iniciarlo
            if not self.is_alive():
                self.restart_count += 1
                
                # Límite de reinicios rápidos
                uptime = time.time() - self.start_time
                if uptime < 60 and self.restart_count > 5:
                    self.log("❌ Demasiados reinicios rápidos. Esperando...")
                    time.sleep(60)
                
                self.log(f"♻️ Restart #{self.restart_count}")
                
                if not self.start_bot():
                    time.sleep(10)
                    continue
                
                self.start_time = time.time()
            
            # Monitorear
            time.sleep(5)
        
        # Cleanup
        self.log("🧹 Limpiando...")
        self.stop_bot()
        self.log("✅ Supervisor finalizado")


if __name__ == "__main__":
    supervisor = BotSupervisor()
    
    try:
        supervisor.run()
    except KeyboardInterrupt:
        print("\n⚠️ Interrupción de teclado")
    except Exception as e:
        print(f"\n💀 Error crítico: {e}")
    finally:
        supervisor.stop_bot()
