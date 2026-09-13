# FinSmart

Aplicación de finanzas personales desarrollada como proyecto de tesis. Permite registrar ingresos y gastos, definir presupuestos y metas de ahorro, gestionar gastos compartidos con otros usuarios, automatizar el pago de servicios recurrentes (Claro, EMCALI, Movistar) y aplica Machine Learning para ayudar al usuario a entender sus finanzas.

## Funcionalidades principales

- **Autenticación y usuarios**: registro, login con JWT.
- **Transacciones**: registro de ingresos y gastos, categorización.
- **Presupuestos** por categoría con alertas.
- **Metas de ahorro** con seguimiento de aportes.
- **Gastos compartidos** entre grupos de usuarios (división y liquidación de saldos).
- **Servicios recurrentes**: pago automatizado de facturas (Claro PSE, EMCALI, Movistar) mediante scraping/RPA.
- **Facturas**: lectura de facturas (QR/escaneo).
- **Notificaciones** por correo (invitaciones a grupos, confirmación de pago, alertas de presupuesto).
- **Inteligencia Artificial / ML** (`backend/services/ai_service.py`, `backend/services/ml_service.py`):
  - Regresión Logística para sugerir categorías de gastos.
  - Isolation Forest para detectar gastos inusuales (anomalías).
  - DBSCAN sobre TF-IDF de descripciones para detectar patrones de gasto recurrentes.

## Stack técnico

- **Backend**: FastAPI + SQLAlchemy + SQLite, autenticación JWT, scikit-learn para los modelos de ML.
- **Frontend**: Next.js (App Router) + TypeScript + Tailwind CSS + Radix UI.
- **Infraestructura**: Docker / docker-compose para desarrollo y producción (Vercel para el frontend, Render/VM para el backend).

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

Para poblar la base de datos con un usuario y transacciones de ejemplo (pensado para poner en evidencia el comportamiento de los tres modelos de ML):

```bash
cd backend
python seed_demo.py
```

## Variables de entorno

Ver `backend/.env.example` (backend) y `.env.example` (variables para `docker-compose.prod.yml`). Como mínimo se requiere `SECRET_KEY`; el resto (SMTP, 2Captcha, etc.) es opcional y los flujos que dependen de ellas se omiten de forma segura si no están configuradas.
