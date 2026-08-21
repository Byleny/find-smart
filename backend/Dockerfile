FROM python:3.12-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Instalar dependencias de sistema para Chromium headless en Debian Bookworm.
# playwright --with-deps falla porque ttf-unifont y ttf-ubuntu-font-family
# fueron renombrados; los instalamos con los nombres correctos primero.
RUN apt-get update && apt-get install -y --no-install-recommends \
        # fuentes (nombres Bookworm)
        fonts-unifont \
        fonts-freefont-ttf \
        fonts-liberation \
        # librerías de sistema requeridas por Chromium
        libnss3 \
        libnspr4 \
        libdbus-1-3 \
        libatk1.0-0 \
        libatk-bridge2.0-0 \
        libcups2 \
        libdrm2 \
        libxkbcommon0 \
        libxcomposite1 \
        libxdamage1 \
        libxfixes3 \
        libxrandr2 \
        libgbm1 \
        libasound2 \
        libpango-1.0-0 \
        libcairo2 \
        libx11-6 \
        libxcb1 \
        libx11-xcb1 \
        libxext6 \
        # Xvfb para display virtual (modo no-headless mejora puntaje reCAPTCHA)
        xvfb \
    && rm -rf /var/lib/apt/lists/* \
    && patchright install chromium

COPY . .

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
