from datetime import date, datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from database import get_db
from models import User, RecurringService, Invoice
from schemas import (
    InvoiceLookupRequest, InvoiceLookupResult, ProviderInfo,
    RecurringServiceCreate, RecurringServiceUpdate, RecurringServiceResponse,
    InvoiceResult, PSEInitResponse, PSEBank, PSEPayRequest, PSEPayResponse,
    EmcaliCaptchaResponse, EmcaliClickRequest, EmcaliSessionRequest,
    ClaroPollStart, ClaroPollRequest, ClaroInitStatus, ClaroOtpRequest, ClaroPayStatus,
)
from security import oauth2_scheme, SECRET_KEY, ALGORITHM
from jose import JWTError, jwt
from services.scraper_service import (
    fetch_invoice as scraper_fetch, PROVIDERS_LIST, get_scraper,
    create_pse_session, get_pse_session,
)
from services.qr_service import generate_payment_qr

router = APIRouter()

# Proveedores con scraper real (no demo)
REAL_SCRAPER_IDS = {p["id"] for p in PROVIDERS_LIST if p.get("real_scraper")}

# Proveedores que ya ofrecen un enlace de pago PSE real (redirección al
# banco), en lugar de solo un QR informativo con los datos de la factura.
# Movistar quedó fuera: su automatización de pago (services/movistar_pse.py)
# dependía de un portal protegido con Cloudflare Turnstile, que bloquea la
# instrumentación de Playwright/patchright sin importar quién interactúe con
# ella (se comprobó incluso con clics genuinos de una persona real vía
# escritorio remoto) — no hay enlace PSE real que ofrecer, así que Movistar
# vuelve al mismo caso que EMCALI/EPM/Codensa: solo el QR informativo.
_PSE_PROVIDERS = {"gdo"}


def _error_portal(mensaje_publico: str, exc: Exception, status_code: int = 502) -> HTTPException:
    """
    Registra la excepción completa en el log del servidor y devuelve al
    cliente solo un mensaje genérico. Las excepciones de Playwright en
    particular traen su log de lanzamiento completo (rutas internas, PIDs,
    flags de Chrome) — exponer eso tal cual en el detail de la respuesta es
    una fuga de información interna, no un mensaje de error útil.
    """
    print(f"[invoices] {mensaje_publico}: {exc!r}")
    return HTTPException(status_code=status_code, detail=mensaje_publico)


def _get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise exc
    except JWTError:
        raise exc
    user = db.query(User).filter(User.id == int(user_id)).first()
    if user is None:
        raise exc
    return user


# ── Providers ──────────────────────────────────────────────────────────────────

@router.get("/providers", response_model=List[ProviderInfo])
async def list_providers(_: User = Depends(_get_current_user)):
    return [ProviderInfo(**p) for p in PROVIDERS_LIST]


# ── Contracts (genérico: soporta cualquier proveedor con scraper real) ─────────

@router.get("/contracts", response_model=List[RecurringServiceResponse])
async def list_contracts(
    provider: Optional[str] = Query(None, description="Filtrar por proveedor"),
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    q = db.query(RecurringService).filter(
        RecurringService.user_id == current_user.id,
        RecurringService.is_active == True,
    )
    if provider:
        q = q.filter(RecurringService.provider == provider.lower())
    else:
        # Solo mostrar contratos de proveedores con scraper real
        q = q.filter(RecurringService.provider.in_(REAL_SCRAPER_IDS))
    return q.order_by(RecurringService.created_at.desc()).all()


@router.post("/contracts", response_model=RecurringServiceResponse, status_code=201)
async def add_contract(
    payload: RecurringServiceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    if payload.provider.lower() not in REAL_SCRAPER_IDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"El proveedor '{payload.provider}' no soporta consulta automática de facturas.",
        )
    existing = db.query(RecurringService).filter(
        RecurringService.user_id == current_user.id,
        RecurringService.provider == payload.provider.lower(),
        RecurringService.account_reference == payload.account_reference,
        RecurringService.is_active == True,
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ya tienes este número de contrato guardado.",
        )
    svc = RecurringService(**payload.model_dump(), user_id=current_user.id)
    db.add(svc)
    db.commit()
    db.refresh(svc)
    return svc


@router.patch("/contracts/{contract_id}", response_model=RecurringServiceResponse)
async def update_contract(
    contract_id: int,
    payload: RecurringServiceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    svc = db.query(RecurringService).filter(
        RecurringService.id == contract_id,
        RecurringService.user_id == current_user.id,
        RecurringService.is_active == True,
    ).first()
    if not svc:
        raise HTTPException(status_code=404, detail="Contrato no encontrado.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(svc, field, value or None)
    db.commit()
    db.refresh(svc)
    return svc


@router.delete("/contracts/{contract_id}", status_code=204)
async def remove_contract(
    contract_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    svc = db.query(RecurringService).filter(
        RecurringService.id == contract_id,
        RecurringService.user_id == current_user.id,
    ).first()
    if not svc:
        raise HTTPException(status_code=404, detail="Contrato no encontrado.")
    svc.is_active = False
    db.commit()


@router.post("/contracts/{contract_id}/fetch", response_model=InvoiceResult)
async def fetch_contract_invoice(
    contract_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    svc = db.query(RecurringService).filter(
        RecurringService.id == contract_id,
        RecurringService.user_id == current_user.id,
        RecurringService.is_active == True,
    ).first()
    if not svc:
        raise HTTPException(status_code=404, detail="Contrato no encontrado.")

    scraper = get_scraper(svc.provider)
    # Datos del pagador: contrato primero, perfil de usuario como fallback
    payer_name    = svc.payer_name    or current_user.full_name
    payer_email   = svc.payer_email   or current_user.email
    payer_phone   = svc.payer_phone   or current_user.phone   or ""
    payer_id_type = svc.payer_id_type or current_user.identification_type or "CC"
    payer_id_num  = svc.payer_id_number or current_user.identification_number or ""
    user_data = {
        "full_name":            payer_name,
        "email":                payer_email,
        "phone":                payer_phone,
        "identification_type":  payer_id_type,
        "identification_number": payer_id_num,
        # Cédula solo del servicio (sin fallback al perfil) — para scrapers que requieren
        # la cédula del titular del contrato, no del usuario de FinSmart.
        "service_id_number":    svc.payer_id_number or "",
        # Movistar: '1' número de línea, '2' referencia de pago
        "payment_identifier":   svc.payment_identifier or "1",
    }

    try:
        result = await run_in_threadpool(scraper.fetch_invoice, svc.account_reference, user_data)
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise _error_portal(f"Error al consultar el portal de {svc.provider.upper()}.", exc)

    # GDO ya ofrece un enlace de pago PSE real (botón "Pagar con PSE" en la
    # tarjeta del contrato); el QR ahí es redundante. Para el resto (EMCALI,
    # EPM, Codensa/Enel, Movistar), que no tienen un flujo PSE propio, el QR
    # sigue siendo la única ayuda de pago.
    if result.portal_blocked or result.is_up_to_date or svc.provider in _PSE_PROVIDERS:
        qr_b64 = ""
    else:
        qr_b64 = await run_in_threadpool(
            generate_payment_qr,
            svc.name, svc.provider, result.reference, result.amount, str(result.due_date),
        )

    if not result.portal_blocked:
        invoice = Invoice(
            service_id=svc.id,
            amount=result.amount,
            due_date=result.due_date,
            qr_data=qr_b64,
        )
        db.add(invoice)
        svc.last_fetched_amount = result.amount if not result.is_up_to_date else None
        svc.last_fetched_at = datetime.utcnow()
        db.commit()

    return InvoiceResult(
        amount=result.amount,
        due_date=result.due_date,
        reference=result.reference,
        qr_base64=qr_b64,
        service_name=svc.name,
        payment_url=result.payment_url,
        is_demo=result.is_demo,
        is_up_to_date=result.is_up_to_date,
        portal_blocked=result.portal_blocked,
        blocked_reason=result.blocked_reason,
    )


# ── Generic lookup (sin guardar contrato) ─────────────────────────────────────

@router.post("/lookup", response_model=InvoiceLookupResult)
async def lookup_invoice(
    payload: InvoiceLookupRequest,
    current_user: User = Depends(_get_current_user),
):
    scraper = get_scraper(payload.provider)
    user_data = {
        "full_name": current_user.full_name,
        "email": current_user.email,
        "phone": current_user.phone or "",
        "identification_type": current_user.identification_type or "CC",
        "identification_number": current_user.identification_number or "",
    }
    try:
        result = await run_in_threadpool(scraper.fetch_invoice, payload.account_reference, user_data)
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise _error_portal("Error al consultar el portal.", exc)

    service_name = payload.service_name or payload.provider.upper()
    if payload.provider in _PSE_PROVIDERS:
        qr_b64 = ""
    else:
        qr_b64 = await run_in_threadpool(
            generate_payment_qr,
            service_name, payload.provider, result.reference, result.amount, str(result.due_date),
        )

    return InvoiceLookupResult(
        amount=result.amount,
        due_date=str(result.due_date),
        reference=result.reference,
        qr_base64=qr_b64,
        service_name=service_name,
        provider=payload.provider,
        payment_url=result.payment_url,
        is_demo=result.is_demo,
        is_up_to_date=result.is_up_to_date,
    )


# ── PSE Payment (GDO) ─────────────────────────────────────────────────────────

@router.post("/contracts/{contract_id}/pse-init", response_model=PSEInitResponse)
async def pse_init(
    contract_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    """
    Inicia sesión de pago PSE para GDO: ejecuta pasos 1-5, guarda JWT en memoria
    y devuelve lista de bancos + datos de factura.

    Es el único llamado al portal en el flujo de pago: registra la factura igual
    que /fetch, de modo que la referencia mostrada sea la misma contra la que
    después se genera el link (GDO emite una referencia nueva en cada consulta).
    """
    svc = db.query(RecurringService).filter(
        RecurringService.id == contract_id,
        RecurringService.user_id == current_user.id,
        RecurringService.is_active == True,
    ).first()
    if not svc:
        raise HTTPException(status_code=404, detail="Contrato no encontrado.")
    if svc.provider != "gdo":
        raise HTTPException(status_code=400, detail="Solo contratos GDO soportan pago PSE.")

    # Sin fallback al perfil FinSmart: GDO valida el correo del titular del
    # contrato, que puede ser otra persona (ej. un contrato familiar).
    email = svc.payer_email or ""
    if not email:
        raise HTTPException(
            status_code=422,
            detail=(
                "Falta el correo del titular de este contrato en GDO. "
                "Agrégalo con el ícono ✏️ de la tarjeta."
            ),
        )

    from services.scraper_service import GDOScraper, CredentialsError
    scraper = GDOScraper()
    try:
        data = await run_in_threadpool(
            scraper.init_pse_session, svc.account_reference, email
        )
    except CredentialsError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except Exception as exc:
        raise _error_portal("Error al iniciar PSE.", exc)

    session_id = create_pse_session(data["jwt"], contract_id, data["amount"])

    if data["is_up_to_date"]:
        svc.last_fetched_amount = None
    else:
        # Sin QR: este flujo ya termina en pse-pay con un enlace real al banco.
        db.add(Invoice(
            service_id=svc.id,
            amount=data["amount"],
            due_date=date.fromisoformat(data["due_date"]),
            qr_data="",
        ))
        svc.last_fetched_amount = data["amount"]
    svc.last_fetched_at = datetime.utcnow()
    db.commit()

    return PSEInitResponse(
        session_id=session_id,
        banks=[PSEBank(**b) for b in data["banks"]],
        amount=data["amount"],
        due_date=data["due_date"],
        reference=data["reference"],
        is_up_to_date=data["is_up_to_date"],
    )


@router.post("/contracts/{contract_id}/pse-pay", response_model=PSEPayResponse)
async def pse_pay(
    contract_id: int,
    payload: PSEPayRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    """
    Genera el link de la pasarela PSE para la sesión abierta en pse-init.
    """
    svc = db.query(RecurringService).filter(
        RecurringService.id == contract_id,
        RecurringService.user_id == current_user.id,
    ).first()
    if not svc:
        raise HTTPException(status_code=404, detail="Contrato no encontrado.")

    session = get_pse_session(payload.session_id)
    if not session or session["contract_id"] != contract_id:
        raise HTTPException(status_code=400, detail="Sesión PSE expirada. Inicia el proceso nuevamente.")

    from services.scraper_service import GDOScraper
    scraper = GDOScraper()
    try:
        pse_url = await run_in_threadpool(
            scraper.get_pse_url,
            session["jwt"], payload.bank_code, session["amount"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except Exception as exc:
        raise _error_portal("Error al obtener URL PSE.", exc)

    return PSEPayResponse(pse_url=pse_url)


# ── EMCALI: consulta con reCAPTCHA resuelto por el usuario ────────────────────

def _emcali_contract(db: Session, contract_id: int, user: User) -> RecurringService:
    svc = db.query(RecurringService).filter(
        RecurringService.id == contract_id,
        RecurringService.user_id == user.id,
        RecurringService.is_active == True,
    ).first()
    if not svc:
        raise HTTPException(status_code=404, detail="Contrato no encontrado.")
    if svc.provider != "emcali":
        raise HTTPException(status_code=400, detail="Este contrato no es de EMCALI.")
    return svc


async def _emcali_respuesta(
    estado: dict, svc: RecurringService, db: Session,
) -> EmcaliCaptchaResponse:
    """
    Traduce el estado del módulo interactivo. Cuando la consulta termina,
    registra la factura igual que /fetch para que el historial quede completo.
    """
    if estado.get("estado") != "listo":
        return EmcaliCaptchaResponse(**estado)

    datos = estado.get("resultado") or {}
    if datos.get("error"):
        raise HTTPException(status_code=502, detail=datos["error"])

    al_dia    = bool(datos.get("is_up_to_date"))
    monto     = float(datos.get("amount") or 0)
    vence     = datos.get("due_date") or str(date.today() + timedelta(days=15))
    referencia = datos.get("reference") or f"EMCALI-{svc.account_reference}"

    qr_b64 = ""
    if not al_dia:
        qr_b64 = await run_in_threadpool(
            generate_payment_qr, svc.name, svc.provider, referencia, monto, vence,
        )
        db.add(Invoice(
            service_id=svc.id, amount=monto,
            due_date=date.fromisoformat(vence), qr_data=qr_b64,
        ))
    svc.last_fetched_amount = None if al_dia else monto
    svc.last_fetched_at = datetime.utcnow()
    db.commit()

    return EmcaliCaptchaResponse(
        estado="listo",
        resultado=InvoiceResult(
            amount=monto,
            due_date=date.fromisoformat(vence),
            reference=referencia,
            qr_base64=qr_b64,
            service_name=svc.name,
            payment_url="https://pagos.emcali.com.co/pagosweb/checkout",
            is_up_to_date=al_dia,
        ),
    )


@router.post("/contracts/{contract_id}/emcali-start", response_model=EmcaliCaptchaResponse)
async def emcali_start(
    contract_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    """
    Abre el portal de EMCALI en un navegador del servidor e intenta el reCAPTCHA.
    Si Google pide el desafío de imágenes, lo devuelve como PNG para que lo
    resuelva el usuario (EMCALI valida el token server-side y su site key está
    restringido por dominio, así que no hay forma de resolverlo dentro de FinSmart).
    """
    svc = _emcali_contract(db, contract_id, current_user)
    from services import emcali_captcha

    try:
        estado = await run_in_threadpool(
            emcali_captcha.iniciar, svc.account_reference, contract_id
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except Exception as exc:
        raise _error_portal("No se pudo abrir el portal de EMCALI.", exc)

    return await _emcali_respuesta(estado, svc, db)


@router.post("/contracts/{contract_id}/emcali-click", response_model=EmcaliCaptchaResponse)
async def emcali_click(
    contract_id: int,
    payload: EmcaliClickRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    """Reenvía al desafío un clic del usuario (coordenadas relativas 0..1)."""
    svc = _emcali_contract(db, contract_id, current_user)
    from services import emcali_captcha

    try:
        estado = await run_in_threadpool(
            emcali_captcha.clic, payload.session_id, payload.x, payload.y
        )
    except KeyError:
        raise HTTPException(
            status_code=400,
            detail="La verificación expiró. Vuelve a consultar la factura.",
        )
    except Exception as exc:
        raise _error_portal("Error en la verificación.", exc)

    return await _emcali_respuesta(estado, svc, db)


@router.post("/contracts/{contract_id}/emcali-status", response_model=EmcaliCaptchaResponse)
async def emcali_status(
    contract_id: int,
    payload: EmcaliSessionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    """Consulta el estado de una verificación en curso."""
    svc = _emcali_contract(db, contract_id, current_user)
    from services import emcali_captcha

    try:
        estado = await run_in_threadpool(emcali_captcha.estado, payload.session_id)
    except KeyError:
        raise HTTPException(
            status_code=400,
            detail="La verificación expiró. Vuelve a consultar la factura.",
        )
    except Exception as exc:
        raise _error_portal("Error en la verificación.", exc)

    return await _emcali_respuesta(estado, svc, db)


@router.post("/contracts/{contract_id}/emcali-cancel", status_code=204)
async def emcali_cancel(
    contract_id: int,
    payload: EmcaliSessionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    """Cierra el navegador si el usuario abandona la verificación."""
    _emcali_contract(db, contract_id, current_user)
    from services import emcali_captcha
    await run_in_threadpool(emcali_captcha.cerrar, payload.session_id)


# ── PSE Payment (Claro) ───────────────────────────────────────────────────────
# Mismo patrón de sondeo que Movistar, con un paso extra: Claro pide un
# código de verificación por SMS entre el primer reCAPTCHA y el segundo, así
# que hay un estado intermedio "otp_requerido" que el frontend muestra como
# un campo de código antes de llegar a la lista de bancos.

_CLARO_TIPO_SERVICIO = {"claro": "Postpago", "claro_hogar": "Hogar y Multiplay"}


def _claro_contract(db: Session, contract_id: int, user: User) -> RecurringService:
    svc = db.query(RecurringService).filter(
        RecurringService.id == contract_id,
        RecurringService.user_id == user.id,
        RecurringService.is_active == True,
    ).first()
    if not svc:
        raise HTTPException(status_code=404, detail="Contrato no encontrado.")
    if svc.provider not in _CLARO_TIPO_SERVICIO:
        raise HTTPException(status_code=400, detail="Este contrato no es de Claro.")
    return svc


def _claro_user_data(current_user: User) -> dict:
    return {
        "full_name": current_user.full_name,
        "email": current_user.email,
        "identification_type": current_user.identification_type or "CC",
        "identification_number": current_user.identification_number or "",
    }


@router.post("/contracts/{contract_id}/claro-pse-init", response_model=ClaroPollStart)
async def claro_pse_init(
    contract_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    svc = _claro_contract(db, contract_id, current_user)
    from services import claro_pse
    tipo_servicio = _CLARO_TIPO_SERVICIO[svc.provider]
    data = await run_in_threadpool(claro_pse.iniciar, svc.account_reference, tipo_servicio)
    return ClaroPollStart(**data)


@router.post("/contracts/{contract_id}/claro-pse-init-status", response_model=ClaroInitStatus)
async def claro_pse_init_status(
    contract_id: int,
    payload: ClaroPollRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    svc = _claro_contract(db, contract_id, current_user)
    from services import claro_pse
    try:
        data = await run_in_threadpool(claro_pse.estado_iniciar, payload.poll_id)
    except KeyError:
        raise HTTPException(status_code=400, detail="Sesión de consulta expirada. Inicia el proceso nuevamente.")
    except Exception as exc:
        raise _error_portal("Error al consultar la factura de Claro.", exc)

    estado = data.get("estado")
    if estado == "consultando":
        return ClaroInitStatus(estado="consultando")
    if estado == "bloqueado":
        raise HTTPException(
            status_code=502,
            detail=(data.get("resultado") or {}).get("blocked_reason") or "Claro no pudo entregar la factura ahora mismo.",
        )
    if estado == "otp_requerido":
        return ClaroInitStatus(estado="otp_requerido", session_id=data["session_id"])

    amount = float(data.get("amount") or 0)
    due_date = data.get("due_date") or str(date.today() + timedelta(days=15))
    reference = data.get("reference") or f"CLARO-{svc.account_reference}"
    db.add(Invoice(service_id=svc.id, amount=amount, due_date=date.today() + timedelta(days=15), qr_data=""))
    svc.last_fetched_amount = amount
    svc.last_fetched_at = datetime.utcnow()
    db.commit()

    return ClaroInitStatus(
        estado="listo",
        session_id=data.get("session_id", ""),
        banks=[PSEBank(**b) for b in data.get("banks", [])],
        amount=amount, due_date=due_date, reference=reference,
    )


@router.post("/contracts/{contract_id}/claro-pse-otp", response_model=ClaroPollStart)
async def claro_pse_otp(
    contract_id: int,
    payload: ClaroOtpRequest,
    current_user: User = Depends(_get_current_user),
    db: Session = Depends(get_db),
):
    _claro_contract(db, contract_id, current_user)
    from services import claro_pse
    try:
        data = await run_in_threadpool(claro_pse.enviar_otp, payload.session_id, payload.codigo)
    except KeyError:
        raise HTTPException(status_code=400, detail="Sesión de Claro expirada. Inicia el proceso nuevamente.")
    except Exception as exc:
        raise _error_portal("Error al enviar el código de verificación.", exc)
    return ClaroPollStart(**data)


@router.post("/contracts/{contract_id}/claro-pse-otp-status", response_model=ClaroInitStatus)
async def claro_pse_otp_status(
    contract_id: int,
    payload: ClaroPollRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    svc = _claro_contract(db, contract_id, current_user)
    from services import claro_pse
    try:
        data = await run_in_threadpool(claro_pse.estado_otp, payload.poll_id)
    except KeyError:
        raise HTTPException(status_code=400, detail="Sesión de verificación expirada. Inicia el proceso nuevamente.")
    except Exception as exc:
        raise _error_portal("Error al verificar el código de Claro.", exc)

    estado = data.get("estado")
    if estado == "consultando":
        return ClaroInitStatus(estado="consultando")
    if estado == "bloqueado":
        raise HTTPException(
            status_code=502,
            detail=(data.get("resultado") or {}).get("blocked_reason") or "Claro no pudo entregar la factura ahora mismo.",
        )
    if estado == "otp_requerido":
        # La página de confirmación caducó (el 2do reCAPTCHA tardó más de lo
        # que Claro tolera) y el backend ya volvió a pedir un código nuevo
        # automáticamente — dispara un SMS nuevo, hay que pedirle al usuario
        # que lo ingrese otra vez con el mismo session_id.
        return ClaroInitStatus(estado="otp_requerido", session_id=data["session_id"])

    amount = float(data.get("amount") or 0)
    due_date = data.get("due_date") or str(date.today() + timedelta(days=15))
    reference = data.get("reference") or f"CLARO-{svc.account_reference}"
    db.add(Invoice(service_id=svc.id, amount=amount, due_date=date.today() + timedelta(days=15), qr_data=""))
    svc.last_fetched_amount = amount
    svc.last_fetched_at = datetime.utcnow()
    db.commit()

    return ClaroInitStatus(
        estado="listo",
        session_id=data.get("session_id", ""),
        banks=[PSEBank(**b) for b in data.get("banks", [])],
        amount=amount, due_date=due_date, reference=reference,
    )


@router.post("/contracts/{contract_id}/claro-pse-pay", response_model=ClaroPollStart)
async def claro_pse_pay(
    contract_id: int,
    payload: PSEPayRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    _claro_contract(db, contract_id, current_user)
    user_data = _claro_user_data(current_user)
    from services import claro_pse
    try:
        poll_id = await run_in_threadpool(claro_pse.pagar, payload.session_id, payload.bank_code, user_data)
    except KeyError:
        raise HTTPException(status_code=400, detail="Sesión PSE de Claro expirada. Inicia el proceso nuevamente.")
    except Exception as exc:
        raise _error_portal("Error al procesar el pago de Claro.", exc)
    return ClaroPollStart(estado="consultando", poll_id=poll_id)


@router.post("/contracts/{contract_id}/claro-pse-pay-status", response_model=ClaroPayStatus)
async def claro_pse_pay_status(
    contract_id: int,
    payload: ClaroPollRequest,
    current_user: User = Depends(_get_current_user),
    db: Session = Depends(get_db),
):
    _claro_contract(db, contract_id, current_user)
    from services import claro_pse
    try:
        data = await run_in_threadpool(claro_pse.estado_pagar, payload.poll_id)
    except KeyError:
        raise HTTPException(status_code=400, detail="Sesión de pago expirada. Inicia el proceso nuevamente.")
    except Exception as exc:
        raise _error_portal("Error al procesar el pago de Claro.", exc)

    if data.get("estado") == "consultando":
        return ClaroPayStatus(estado="consultando")
    return ClaroPayStatus(estado="listo", pse_url=data.get("redirect_url"))
