FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    MESAYA_DB=/app/data/mesaya.db MESAYA_UPLOADS=/app/data/uploads MESAYA_BACKUP_DIR=/app/data/backups

# OCR local (Tesseract + español) para leer fotos y PDF escaneados sin IA. Si no lo necesitas, quita esta línea (la app funciona igual).
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-spa tesseract-ocr-eng     && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY backend/web ./web
COPY backend/seed.py .

# Usuario sin privilegios; todo lo que se guarda vive en /app/data (un solo volumen)
RUN useradd --uid 1000 --create-home mesaya && mkdir -p /app/data && chown -R mesaya:mesaya /app
USER mesaya
VOLUME ["/app/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4).status == 200 else 1)"

# UN solo proceso: el tiempo real (SSE) y los límites de intentos viven en memoria.
# --proxy-headers: toma la IP real del cliente desde el proxy (Caddy/Fly). No expongas este puerto a internet sin proxy.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
