# FinSmart

Aplicación de finanzas personales desarrollada como proyecto de tesis. Permite registrar ingresos y gastos, definir presupuestos y metas de ahorro, gestionar gastos compartidos con otros usuarios, consultar y pagar automáticamente por PSE las facturas de GDO (Gases de Occidente), hacer seguimiento a otros servicios recurrentes (EMCALI, Claro, Movistar, Tigo, Celsia) enlazando directo a sus portales oficiales de pago, y aplica Machine Learning para ayudar al usuario a entender sus finanzas.

## Funcionalidades principales

- **Autenticación y usuarios**: registro, login con JWT.
- **Transacciones**: registro de ingresos y gastos, categorización.
- **Presupuestos** por categoría con alertas.
- **Metas de ahorro** con seguimiento de aportes.
- **Gastos compartidos** entre grupos de usuarios (división y liquidación de saldos).
- **Servicios recurrentes y facturas**: registro de contratos de servicios (EMCALI, Claro, Movistar, Tigo, Celsia, GDO). Para GDO, consulta automática del monto y la fecha de vencimiento mediante scraping/RPA del portal, con generación del enlace de pago PSE. EMCALI y Claro también tienen automatización probada de punta a punta (reCAPTCHA resuelto vía 2Captcha o retransmitido al usuario), pero se dejó fuera del flujo principal por la poca confiabilidad del paso final de confirmación (demoras de hasta minutos o rechazos intermitentes sin causa clara); Movistar sí quedó bloqueado de forma permanente por Cloudflare Turnstile. En estos tres casos, y en Tigo/Celsia, se lleva al usuario directo a su portal oficial para consultar y pagar.
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
│   ├── services/              # Lógica de negocio, ML/IA y automatización de pagos
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

## Variables de entorno

Ver `backend/.env.example` (backend) y `.env.example` (variables para `docker-compose.prod.yml`). Como mínimo se requiere `SECRET_KEY`; el resto (SMTP, 2Captcha, etc.) es opcional y los flujos que dependen de ellas se omiten de forma segura si no están configuradas.
