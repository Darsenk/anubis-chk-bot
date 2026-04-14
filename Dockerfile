# Usar Python 3.11 slim
FROM python:3.11-slim

# Establecer directorio de trabajo
WORKDIR /app

# Copiar archivos de requisitos primero (para cachear la capa)
COPY requirements.txt .

# Instalar dependencias
RUN pip install --no-cache-dir -r requirements.txt

# Copiar todos los archivos del proyecto
COPY . .

# Exponer puerto (Koyeb lo necesita aunque no uses HTTP)
EXPOSE 8080

# Comando para ejecutar el bot
CMD ["python", "bot.py"]
