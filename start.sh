#!/bin/bash

echo "════════════════════════════════════════════════════════"
echo "🚀 ANUBIS CHK — INICIANDO EN KOYEB"
echo "════════════════════════════════════════════════════════"
echo ""

# Instalar dependencias
echo "📦 Instalando dependencias..."
pip install --no-cache-dir -r requirements.txt

if [ $? -ne 0 ]; then
    echo "❌ Error instalando dependencias"
    exit 1
fi

echo "✅ Dependencias instaladas"
echo ""

# Verificar variables críticas
echo "🔍 Verificando variables de entorno..."
if [ -z "$TELEGRAM_TOKEN" ]; then
    echo "❌ TELEGRAM_TOKEN no configurado"
    exit 1
fi

if [ -z "$ADMIN_CHAT_ID" ]; then
    echo "❌ ADMIN_CHAT_ID no configurado"
    exit 1
fi

if [ -z "$FIREBASE_CREDENTIALS" ]; then
    echo "❌ FIREBASE_CREDENTIALS no configurado"
    exit 1
fi

echo "✅ Variables configuradas correctamente"
echo ""

# Iniciar bot
echo "🚀 Iniciando ANUBIS CHK en modo WEBHOOK..."
echo ""
python bot.py
