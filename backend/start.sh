#!/bin/sh
# Arranque del backend: Xvfb (pantalla virtual) + semilla + uvicorn.
#
# Chrome real (no headless) sobre esta pantalla mejora el puntaje de los
# reCAPTCHA v2/v3 que resuelven los scrapers (EMCALI, EPM, Codensa, Claro).
# Xvfb corre supervisado en un bucle propio: se cayó alguna vez sin que nada
# lo notara, dejando un socket viejo en /tmp/.X11-unix que engañaba el
# chequeo de "¿ya está listo?" y hacía fallar el lanzamiento del navegador
# con "Missing X server or $DISPLAY" horas después. Si Xvfb muere, este
# bucle lo vuelve a levantar solo.
(
  while true; do
    rm -f /tmp/.X11-unix/X99 /tmp/.X99-lock
    Xvfb :99 -screen 0 1920x1080x24 >>/tmp/xvfb.log 2>&1
    sleep 1
  done
) &

i=0
while [ ! -e /tmp/.X11-unix/X99 ] && [ "$i" -lt 50 ]; do
  sleep 0.2
  i=$((i + 1))
done

python seed_completo.py
exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}" "$@"
