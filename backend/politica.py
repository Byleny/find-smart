"""Política de tratamiento de datos personales (Ley 1581 de 2012 y Decreto 1377 de 2013).

El texto completo se publica en la página /privacidad del frontend. Aquí viven la versión
vigente y los datos del responsable, que la página consulta en GET /auth/politica.
"""
import os

# Cambiar la versión obliga a todos los usuarios a aceptar de nuevo la política.
POLITICA_VERSION = "1.0"
POLITICA_VIGENTE_DESDE = "2026-10-15"


def datos_de_la_politica() -> dict:
    return {
        "version": POLITICA_VERSION,
        "vigente_desde": POLITICA_VIGENTE_DESDE,
        "responsable": os.getenv("POLITICA_RESPONSABLE", "Bylen Yesid Naspiran Realpe"),
        "domicilio": os.getenv("POLITICA_DOMICILIO", "Santiago de Cali, Valle del Cauca, Colombia"),
        "correo": os.getenv("POLITICA_CORREO", "bynaspiranr@correo.usbcali.edu.co"),
        "telefono": os.getenv("POLITICA_TELEFONO", ""),
    }
