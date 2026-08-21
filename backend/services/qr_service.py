import json
import base64
from io import BytesIO

import qrcode
from qrcode.image.pil import PilImage


def generate_payment_qr(
    service_name: str,
    provider: str,
    reference: str,
    amount: float,
    due_date: str,
) -> str:
    data = {
        "servicio": service_name,
        "proveedor": provider,
        "referencia": reference,
        "valor": amount,
        "vencimiento": due_date,
    }
    payload = json.dumps(data, ensure_ascii=False)

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(payload)
    qr.make(fit=True)

    img: PilImage = qr.make_image(fill_color="black", back_color="white")

    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    return base64.b64encode(buffer.read()).decode("utf-8")
