import os
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Optional

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from dotenv import load_dotenv

load_dotenv()

# Sin valor por defecto en el código: una clave conocida permitiría a cualquiera firmar tokens
# válidos. Si falta o es corta, se usa una aleatoria por proceso (las sesiones se pierden al
# reiniciar el backend, pero nadie puede predecir la clave).
SECRET_KEY = os.getenv("SECRET_KEY", "")
if len(SECRET_KEY) < 32:
    print("[security] SECRET_KEY ausente o con menos de 32 caracteres: se usa una clave aleatoria temporal.")
    SECRET_KEY = secrets.token_urlsafe(48)
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_DAYS = int(os.getenv("ACCESS_TOKEN_EXPIRE_DAYS", "7"))

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())


# Hash de una contraseña que nadie conoce. Cuando el correo no existe, el login lo verifica
# igual, para que la respuesta tarde lo mismo que con una cuenta real y el tiempo no delate
# qué correos están registrados.
_HASH_SIN_CUENTA = bcrypt.hashpw(secrets.token_bytes(16), bcrypt.gensalt()).decode()


def verify_password_or_dummy(plain_password: str, hashed_password: Optional[str]) -> bool:
    if hashed_password is None:
        verify_password(plain_password, _HASH_SIN_CUENTA)
        return False
    return verify_password(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


class LimitadorDeIntentos:
    """Bloquea temporalmente una cuenta tras varios inicios de sesión fallidos en una ventana.

    Se cuenta por correo y no por IP: detrás del proxy de Next.js todas las solicitudes
    llegan al backend desde la misma dirección, así que limitar por IP bloquearía a todos.
    El estado vive en memoria del proceso, suficiente para un único contenedor de backend.
    """

    def __init__(self, max_intentos: int, ventana_segundos: int, reloj=time.monotonic):
        self.max_intentos = max_intentos
        self.ventana = ventana_segundos
        self.reloj = reloj
        self._fallos: dict[str, deque] = defaultdict(deque)
        self._lock = Lock()

    def _purgar(self, clave: str, ahora: float) -> deque:
        fallos = self._fallos[clave]
        while fallos and ahora - fallos[0] >= self.ventana:
            fallos.popleft()
        if not fallos:
            del self._fallos[clave]
            return deque()
        return fallos

    def segundos_de_bloqueo(self, clave: str) -> int:
        with self._lock:
            ahora = self.reloj()
            fallos = self._purgar(clave, ahora)
            if len(fallos) >= self.max_intentos:
                return int(self.ventana - (ahora - fallos[0])) + 1
            return 0

    def registrar_fallo(self, clave: str) -> None:
        with self._lock:
            self._fallos[clave].append(self.reloj())

    # Para límites que cuentan cada intento y no solo los fallidos.
    registrar_intento = registrar_fallo

    def reiniciar(self, clave: str) -> None:
        with self._lock:
            self._fallos.pop(clave, None)


limitador_login = LimitadorDeIntentos(
    max_intentos=int(os.getenv("LOGIN_MAX_INTENTOS", "5")),
    ventana_segundos=int(os.getenv("LOGIN_VENTANA_MINUTOS", "15")) * 60,
)

# Agregar un correo a un grupo responde distinto si el correo tiene cuenta (se envía una
# invitación) o no (se agrega como contacto). Para que esa diferencia no sirva para recorrer
# listas de correos, cada usuario tiene un tope de miembros agregados por hora.
limitador_miembros = LimitadorDeIntentos(
    max_intentos=int(os.getenv("MIEMBROS_MAX_POR_HORA", "20")),
    ventana_segundos=3600,
)
