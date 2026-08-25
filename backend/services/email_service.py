"""
Aviso por correo al email registrado del usuario.

Por qué existe este módulo
--------------------------
Las notificaciones del bell (invitación a grupo, solicitud de confirmar un
pago, alerta de presupuesto) solo se ven si el usuario abre la app. Este
módulo manda el mismo aviso por correo a la dirección con la que el usuario
se registró — nunca a un correo distinto que alguien pueda escribir a mano —
para que no dependa de que entre a mirar la campanita.

Se llama siempre vía BackgroundTasks: la conexión SMTP puede tardar varios
segundos, y si no hay credenciales configuradas (dev local, o un despliegue
que todavía no las puso) send_email() simplemente no hace nada — el flujo
normal de la app (crear el grupo, registrar el gasto, etc.) no puede depender
de que el correo salga bien.
"""
from __future__ import annotations

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger("finsmart.email")

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER)

# Nombre que ve el destinatario como remitente (ej. "FinSmart <tucorreo@gmail.com>"),
# independiente del nombre real de la cuenta de correo que se use para enviar.
APP_NAME = os.getenv("EMAIL_FROM_NAME", "FinSmart")
APP_URL = os.getenv("APP_PUBLIC_URL", "")


def _configurado() -> bool:
    return bool(SMTP_HOST and SMTP_USER and SMTP_PASSWORD)


def cop(valor: float) -> str:
    """`1234567` → `$ 1.234.567`, igual que formatCOP en el frontend."""
    return f"$ {valor:,.0f}".replace(",", ".")


def _plantilla(titulo: str, parrafos: list[str]) -> str:
    cuerpo = "".join(
        f'<p style="margin:0 0 16px;font-size:15px;line-height:1.55;color:#3a3a3a;">{p}</p>'
        for p in parrafos
    )
    boton = (
        f'''<a href="{APP_URL}" style="display:inline-block;margin-top:8px;padding:11px 22px;
            background:#0A0A0A;color:#ffffff;text-decoration:none;border-radius:8px;
            font-size:14px;font-weight:600;">Abrir FinSmart</a>'''
        if APP_URL else ""
    )
    return f"""
    <div style="background:#f2f2f0;padding:32px 16px;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;">
      <div style="max-width:460px;margin:0 auto;background:#ffffff;border-radius:16px;overflow:hidden;
                  border:1px solid #ececec;">
        <div style="background:#0A0A0A;padding:20px 28px;">
          <span style="color:#ffffff;font-weight:800;font-size:16px;letter-spacing:-0.01em;">{APP_NAME}</span>
        </div>
        <div style="padding:28px;">
          <h1 style="margin:0 0 16px;font-size:19px;font-weight:800;color:#0A0A0A;letter-spacing:-0.01em;">{titulo}</h1>
          {cuerpo}
          {boton}
        </div>
        <div style="padding:16px 28px;border-top:1px solid #ececec;">
          <p style="margin:0;font-size:11px;color:#a0a0a0;">
            Recibiste este correo porque tienes una cuenta en {APP_NAME} registrada con esta dirección.
          </p>
        </div>
      </div>
    </div>
    """


def send_email(to: str, subject: str, html_body: str) -> bool:
    if not to:
        return False
    if not _configurado():
        logger.info("SMTP no configurado; se omite el correo a %s (%s)", to, subject)
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{APP_NAME} <{SMTP_FROM}>"
        msg["To"] = to
        msg.attach(MIMEText(html_body, "html", "utf-8"))
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_FROM, [to], msg.as_string())
        return True
    except Exception:
        logger.exception("No se pudo enviar el correo a %s", to)
        return False


# ── Avisos concretos ─────────────────────────────────────────────────────────

def send_group_invite_email(to: str, member_name: str, group_name: str, inviter_name: str) -> bool:
    subject = f"{inviter_name} te invitó al grupo \"{group_name}\""
    body = _plantilla("Te invitaron a un grupo compartido", [
        f"<strong>{inviter_name}</strong> te agregó como <strong>{member_name}</strong> al grupo "
        f"“<strong>{group_name}</strong>” en {APP_NAME}.",
        "Entra a tus notificaciones para aceptar o rechazar la invitación. Si aceptas, verás este "
        "grupo y sus gastos compartidos en tu cuenta.",
    ])
    return send_email(to, subject, body)


def send_settle_request_email(to: str, debtor_name: str, amount_text: str, group_name: str, obligations: str) -> bool:
    subject = f"{debtor_name} dice haberte pagado {amount_text}"
    body = _plantilla("Confirmación de pago pendiente", [
        f"<strong>{debtor_name}</strong> marcó como pagada su deuda de <strong>{amount_text}</strong> "
        f"contigo en el grupo “<strong>{group_name}</strong>”: {obligations}.",
        "Entra a tus notificaciones para confirmar que recibiste el dinero. Mientras no lo confirmes, "
        "la deuda sigue apareciendo como pendiente.",
    ])
    return send_email(to, subject, body)


def send_budget_alert_email(to: str, category: str, spent: float, limit: float, exceeded: bool) -> bool:
    pct = round(spent / limit * 100) if limit else 0
    titulo = "Superaste tu presupuesto" if exceeded else "Tu presupuesto está por agotarse"
    subject = f"{titulo}: {category} ({pct}%)"
    mensaje = (
        f"Ya gastaste <strong>{cop(spent)}</strong> en <strong>{category}</strong> este mes, "
        f"{'superando' if exceeded else 'llegando al'} {pct}% de tu límite de <strong>{cop(limit)}</strong>."
    )
    body = _plantilla(titulo, [
        mensaje,
        "Puedes ajustar el límite o revisar tus gastos de este mes en la sección de Presupuestos.",
    ])
    return send_email(to, subject, body)
