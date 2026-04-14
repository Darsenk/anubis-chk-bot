#!/bin/bash

# ══════════════════════════════════════════════════════════════
# SCRIPT DE INICIO RÁPIDO — ANUBIS CHK
# ══════════════════════════════════════════════════════════════

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║              𓂀 ANUBIS CHK — INICIO RÁPIDO               ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# Colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Verificar Python
echo "🔍 Verificando Python..."
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python3 no encontrado${NC}"
    exit 1
fi

PYTHON_VERSION=$(python3 --version)
echo -e "${GREEN}✅ $PYTHON_VERSION${NC}"

# Verificar pip
echo "🔍 Verificando pip..."
if ! command -v pip3 &> /dev/null; then
    echo -e "${RED}❌ pip3 no encontrado${NC}"
    exit 1
fi
echo -e "${GREEN}✅ pip encontrado${NC}"

# Instalar dependencias si no existen
echo ""
echo "📦 Verificando dependencias..."
if ! python3 -c "import requests" &> /dev/null || ! python3 -c "import firebase_admin" &> /dev/null; then
    echo -e "${YELLOW}⚠️ Instalando dependencias...${NC}"
    pip3 install -r requirements.txt
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ Dependencias instaladas${NC}"
    else
        echo -e "${RED}❌ Error instalando dependencias${NC}"
        exit 1
    fi
else
    echo -e "${GREEN}✅ Dependencias ya instaladas${NC}"
fi

# Verificar variables de entorno
echo ""
echo "🔍 Verificando configuración..."
if [ -z "$TELEGRAM_TOKEN" ] || [ -z "$ADMIN_CHAT_ID" ] || [ -z "$FIREBASE_CREDENTIALS" ]; then
    echo -e "${YELLOW}⚠️ Variables de entorno no encontradas${NC}"
    echo ""
    echo "Asegúrate de configurar:"
    echo "  export TELEGRAM_TOKEN=your_token"
    echo "  export ADMIN_CHAT_ID=your_chat_id"
    echo "  export FIREBASE_CREDENTIALS='{...}'"
    echo ""
    echo -e "${YELLOW}¿Quieres continuar de todas formas? (y/N)${NC}"
    read -r response
    if [[ ! "$response" =~ ^[Yy]$ ]]; then
        exit 1
    fi
else
    echo -e "${GREEN}✅ Variables de entorno configuradas${NC}"
fi

# Ejecutar tests
echo ""
echo "🧪 Ejecutando tests de diagnóstico..."
echo ""
python3 test_bot.py

if [ $? -ne 0 ]; then
    echo ""
    echo -e "${RED}❌ Tests fallaron${NC}"
    echo -e "${YELLOW}¿Quieres iniciar el bot de todas formas? (y/N)${NC}"
    read -r response
    if [[ ! "$response" =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Preguntar modo de ejecución
echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║                    MODO DE EJECUCIÓN                     ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "1) Modo directo (python bot.py)"
echo "2) Con supervisor (recomendado)"
echo "3) Cancelar"
echo ""
echo -n "Selecciona una opción [1-3]: "
read -r option

case $option in
    1)
        echo ""
        echo -e "${GREEN}🚀 Iniciando bot en modo directo...${NC}"
        echo ""
        python3 bot.py
        ;;
    2)
        echo ""
        echo -e "${GREEN}🚀 Iniciando bot con supervisor...${NC}"
        echo ""
        python3 supervisor.py
        ;;
    3)
        echo ""
        echo "Operación cancelada"
        exit 0
        ;;
    *)
        echo ""
        echo -e "${RED}❌ Opción inválida${NC}"
        exit 1
        ;;
esac
