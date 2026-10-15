# FinSmart

Aplicación de finanzas personales desarrollada como proyecto de tesis. Permite registrar ingresos y gastos, definir presupuestos y metas de ahorro, gestionar gastos compartidos con otros usuarios, consultar las facturas de GDO (Gases de Occidente) y llegar a la pasarela PSE del banco con el valor ya cargado, hacer seguimiento a otros servicios recurrentes (EMCALI, Claro, Movistar, Tigo, Celsia) enlazando directo a sus portales oficiales de pago, y aplica Machine Learning para ayudar al usuario a entender sus finanzas.

## Funcionalidades principales

- **Autenticación y usuarios**: registro, login con JWT y autorización para el tratamiento de datos (Ley 1581 de 2012): el registro exige aceptar la política publicada en `/privacidad`, y una cuenta sin la versión vigente aceptada no accede a sus datos hasta aceptarla.
- **Transacciones**: registro de ingresos y gastos, categorización.
- **Presupuestos** por categoría con alertas.
- **Metas de ahorro** con seguimiento de aportes.
- **Gastos compartidos** entre grupos de usuarios (división y liquidación de saldos).
- **Servicios recurrentes y facturas**: registro de contratos de servicios (EMCALI, Claro, Movistar, Tigo, Celsia, GDO). Para GDO, al pulsar *Consultar factura* el backend obtiene del portal el monto, la fecha de vencimiento y la referencia, y genera el enlace a la pasarela PSE del banco que elija el usuario. Antes de ese clic no se consulta nada, y la app nunca ejecuta pagos: el usuario los completa en su banco y luego puede reportarlos como gasto. Claro tiene automatización probada de punta a punta (reCAPTCHA resuelto vía 2Captcha y código de verificación por SMS), pero se dejó fuera del flujo principal porque no es confiable de forma sostenida: el código SMS a veces se demora y esa demora hace que la operación falle. Para EMCALI se implementó una automatización que retransmite el reCAPTCHA al usuario, pero no logró completar ninguna consulta. Movistar quedó bloqueado: su formulario de pago usa Cloudflare Turnstile y, en las pruebas más recientes, el servidor rechaza incluso la consulta automática de la factura. En estos tres casos, y en Tigo/Celsia, se lleva al usuario directo a su portal oficial para consultar y pagar.
- **Notificaciones** por correo (invitaciones a grupos, confirmación de pago, alertas de presupuesto).
- **Inteligencia Artificial / ML** (`backend/services/ai_service.py`, `backend/services/ml_service.py`):
  - Regresión Logística para sugerir categorías de gastos.
  - Isolation Forest para detectar gastos inusuales (anomalías).
  - DBSCAN sobre TF-IDF de descripciones para detectar patrones de gasto recurrentes.

## Stack técnico

- **Backend**: FastAPI + SQLAlchemy + SQLite, autenticación JWT, scikit-learn para los modelos de ML.
- **Frontend**: Next.js (App Router) + TypeScript + Tailwind CSS + Radix UI.
- **Infraestructura**: Docker / docker-compose para desarrollo y producción. En producción, backend y frontend corren como dos contenedores en la misma VM (`docker-compose.prod.yml`): el frontend se publica en el puerto asignado por el hosting (5016) y el backend queda solo accesible internamente en la red de docker-compose, a través del proxy de rewrites de Next.js — sin proxy reverso propio; dominio/SSL se manejan fuera del repositorio.

## Estructura del proyecto

```
.
├── backend/                # API FastAPI
│   ├── main.py              # Punto de entrada de la app
│   ├── models.py            # Modelos SQLAlchemy
│   ├── schemas.py           # Esquemas Pydantic
│   ├── database.py          # Configuración de la base de datos
│   ├── routers/              # Endpoints (auth, transactions, budgets, goals, shared, recurring, invoices, notifications)
│   ├── services/              # Lógica de negocio, ML/IA y consulta de facturas
│   ├── ml_models/             # Modelos entrenados serializados
│   └── seed_demo.py           # Script para poblar la base de datos con datos de demostración
├── frontend/                # Aplicación Next.js
│   ├── app/                   # Rutas (App Router)
│   ├── components/            # Componentes de UI
│   ├── contexts/               # Contextos de React (auth, etc.)
│   └── lib/                     # Utilidades y cliente de API
├── docker-compose.yml         # Orquestación para desarrollo local
└── docker-compose.prod.yml    # Orquestación para despliegue en producción
```

## Cómo ejecutar el proyecto

### Opción 1: Docker (recomendado)

```bash
docker compose up --build
```

- Backend disponible en `http://localhost:8000` (docs en `/docs`).
- Frontend disponible en `http://localhost:3000`.

### Opción 2: Manual

**Backend**

```bash
cd backend
python -m venv venv
venv\Scripts\activate        # En Windows
pip install -r requirements.txt
copy .env.example .env       # Completar variables de entorno
uvicorn main:app --reload
```

**Frontend**

```bash
cd frontend
npm install
npm run dev
```

### Datos de demostración

> Al levantar el backend con Docker, `start.sh` ya ejecuta automáticamente `backend/seed_completo.py`, dejando precargada la cuenta `demo@finsmart.co` / `demo1234` (además de `carlos@finsmart.co` y `lucia@finsmart.co`) con ~6 meses de transacciones, un grupo de gastos compartidos, presupuestos y metas de ahorro.

El script de abajo agrega un dataset alternativo sobre el mismo usuario `demo@finsmart.co`, pensado específicamente para poner en evidencia el comportamiento de los tres modelos de ML (usado normalmente en instalaciones manuales, sin Docker):

```bash
cd backend
python seed_demo.py
```

## Pruebas automatizadas

La carpeta `backend/tests` contiene 87 pruebas (funcionales, de integración, de seguridad y unitarias del módulo de IA), con casos negativos y de límite. Corren sobre una base de datos temporal cifrada con SQLCipher, así que no tocan `finsmart.db` ni los modelos de `ml_models/`.

```bash
cd backend
pip install -r requirements-dev.txt
pytest
```

Todas pasan. La suite incluye los casos de seguridad descritos abajo (enumeración de cuentas, manejo de errores, clave JWT, bloqueo de intentos y cifrado).

## Variables de entorno

Ver `backend/.env.example` (backend) y `.env.example` (variables para `docker-compose.prod.yml`). Como mínimo se requiere `SECRET_KEY` (32 caracteres o más; si falta, el backend usa una clave aleatoria por arranque y las sesiones se cierran al reiniciar); el resto (SMTP, 2Captcha, etc.) es opcional y los flujos que dependen de ellas se omiten de forma segura si no están configuradas.

### Seguridad de la base de datos y del inicio de sesión

- **Cifrado en reposo:** si se define `DB_ENCRYPTION_KEY`, la base SQLite se abre con SQLCipher (AES-256) y el archivo queda ilegible sin la clave. Para cifrar una base existente sin perder datos, con el backend detenido:

  ```bash
  cd backend
  DB_ENCRYPTION_KEY=<clave> python cifrar_base_de_datos.py finsmart.db finsmart_cifrada.db
  ```

  El script verifica que la copia tenga las mismas filas; después se reemplaza el archivo original por la copia y se arranca el backend con la misma clave. Sin la clave, los datos no se pueden recuperar: guárdala fuera del servidor.
- **Bloqueo de intentos:** tras 5 inicios de sesión fallidos sobre una misma cuenta en 15 minutos, esa cuenta responde HTTP 429 hasta que pasa la ventana (`LOGIN_MAX_INTENTOS` y `LOGIN_VENTANA_MINUTOS` lo ajustan).
- **Sin enumeración de cuentas:** el registro y el inicio de sesión responden con mensajes genéricos y hacen la misma verificación bcrypt exista o no la cuenta. Agregar integrantes a grupos tiene un tope por usuario (`MIEMBROS_MAX_POR_HORA`, 20 por defecto), porque la invitación revela si el correo tiene cuenta.
- **Contraseñas:** de 8 a 72 caracteres (bcrypt solo procesa los primeros 72 bytes).
- **Errores internos:** se registran en el log del servidor y al cliente solo le llega un mensaje genérico.
- **Política de tratamiento de datos:** la versión vigente está en `backend/politica.py` (cambiarla obliga a todos a aceptarla de nuevo). El responsable, el domicilio, el correo y el teléfono que muestra la página se pueden cambiar con `POLITICA_RESPONSABLE`, `POLITICA_DOMICILIO`, `POLITICA_CORREO` y `POLITICA_TELEFONO`.
