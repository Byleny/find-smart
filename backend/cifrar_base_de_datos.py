"""Crea una copia cifrada con SQLCipher de una base de datos SQLite existente.

Uso, con el backend detenido y DB_ENCRYPTION_KEY definida en el entorno:

    python cifrar_base_de_datos.py finsmart.db finsmart_cifrada.db

Después de revisar la verificación, reemplazar el archivo original por la copia
cifrada y arrancar el backend con la misma DB_ENCRYPTION_KEY.
"""
import os
import sys

import sqlcipher3


def _literal(clave: str) -> str:
    return "'" + clave.replace("'", "''") + "'"


def contar_filas(conn) -> dict:
    tablas = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    return {t: conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in tablas}


def cifrar(origen: str, destino: str, clave: str) -> dict:
    if not clave:
        raise SystemExit("Define DB_ENCRYPTION_KEY antes de ejecutar el script.")
    if not os.path.exists(origen):
        raise SystemExit(f"No existe {origen}")
    if os.path.exists(destino):
        raise SystemExit(f"{destino} ya existe; elige otra ruta para no sobrescribirlo.")

    conn = sqlcipher3.connect(origen)
    filas_origen = contar_filas(conn)
    conn.execute(f"ATTACH DATABASE {_literal(destino)} AS cifrada KEY {_literal(clave)}")
    conn.execute("SELECT sqlcipher_export('cifrada')")
    conn.execute("DETACH DATABASE cifrada")
    conn.close()

    verif = sqlcipher3.connect(destino)
    verif.execute(f"PRAGMA key = {_literal(clave)}")
    filas_destino = contar_filas(verif)
    verif.close()

    if filas_origen != filas_destino:
        raise SystemExit(f"La copia no coincide con el original: {filas_origen} != {filas_destino}")
    return filas_destino


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    resultado = cifrar(sys.argv[1], sys.argv[2], os.getenv("DB_ENCRYPTION_KEY", ""))
    print(f"Copia cifrada verificada: {sum(resultado.values())} filas en {len(resultado)} tablas.")
