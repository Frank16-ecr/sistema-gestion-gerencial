# SGG · Sistema de Gestión Gerencial

[![CI](https://github.com/Frank16-ecr/sistema-gestion-gerencial/actions/workflows/ci.yml/badge.svg)](https://github.com/Frank16-ecr/sistema-gestion-gerencial/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue)](https://www.python.org/downloads/)
[![Django](https://img.shields.io/badge/django-4.2-green)](https://www.djangoproject.com/)
[![Licencia: MIT](https://img.shields.io/badge/licencia-MIT-yellow.svg)](LICENSE)

Backend financiero y gerencial **multiempresa** construido con Django REST Framework, con un **panel web** de indicadores. Reúne en una sola API la contabilidad, facturación, cobros, gastos, nómina, obligaciones fiscales, bancos, divisas, presupuestos, inversiones, reportes y auditoría de varias empresas, con permisos por rol en cada una.

> SGG parte del proyecto de código abierto *Zelani Finance Module* (licencia MIT) y lo amplía con seguridad por empresa, presupuestos, inversiones, resumen gerencial, panel web y configuración por país.

## Índice

1. [Funcionalidades](#1-funcionalidades)
2. [Tecnologías](#2-tecnologías)
3. [Puesta en marcha](#3-puesta-en-marcha)
4. [Configuración](#4-configuración)
5. [Seguridad y roles](#5-seguridad-y-roles)
6. [Adaptar a tu país o empresa](#6-adaptar-a-tu-país-o-empresa)
7. [Panel gerencial](#7-panel-gerencial)
8. [API](#8-api)
9. [Módulos](#9-módulos)
10. [Pruebas y calidad](#10-pruebas-y-calidad)
11. [Estructura del proyecto](#11-estructura-del-proyecto)
12. [Notas de operación](#12-notas-de-operación)
13. [Licencia](#13-licencia)

## 1. Funcionalidades

- **Multiempresa** con aislamiento estricto: cada usuario solo ve y modifica las empresas donde tiene un rol.
- **Roles por empresa**: administrador, gerente, analista, auditor y solo lectura.
- **Contabilidad** de partida doble: plan de cuentas, asientos y líneas, en varias monedas.
- **Facturación y cobros**: notas de cobro con su ciclo de vida, pagos, diferencias de cambio y retenciones.
- **Gastos y reembolsos** con flujo de aprobación.
- **Nómina** con impuestos y seguridad social **configurables por empresa**.
- **Obligaciones fiscales** con vencimientos y estados.
- **Bancos y caja chica**, conciliaciones y cheques.
- **Divisas**: tipos de cambio por fecha.
- **Presupuestos**: planificado contra ejecutado, por categoría.
- **Inversiones**: aportes, rendimientos, retiros y portafolio por moneda.
- **Reportes**: estado de resultados, balance general, cuentas por cobrar, resumen de nómina y **resumen gerencial con alertas**.
- **Panel web** responsive, con modo claro y oscuro.
- **Bitácora de auditoría**.

## 2. Tecnologías

- Python 3.11 / 3.12 y Django 4.2
- Django REST Framework, django-filter y drf-spectacular (OpenAPI, Swagger, ReDoc)
- PostgreSQL en ejecución; SQLite en memoria para las pruebas
- Celery y Redis para tareas en segundo plano
- Docker y Docker Compose

## 3. Puesta en marcha

### Opción A: Docker (recomendada)

```bash
git clone https://github.com/Frank16-ecr/sistema-gestion-gerencial.git
cd sistema-gestion-gerencial
cp .env.example .env
docker compose up --build
docker compose exec web python manage.py createsuperuser
```

### Opción B: entorno virtual local

```bash
git clone https://github.com/Frank16-ecr/sistema-gestion-gerencial.git
cd sistema-gestion-gerencial
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Abre `http://localhost:8000/` para el panel, `/api/docs/` para la API y `/admin/` para la administración.

Los procesos de Celery van en terminales aparte:

```bash
celery -A sgg worker -l info
celery -A sgg beat -l info
```

### Comandos de `make`

```bash
make help         # lista todos los comandos
make install-dev  # dependencias de desarrollo
make migrate
make run
make pytest       # pruebas
make coverage     # pruebas con cobertura
make lint
make docker-up
```

## 4. Configuración

Copia `.env.example` a `.env` y ajusta:

| Variable | Ejemplo | Para qué sirve |
| --- | --- | --- |
| `SECRET_KEY` | `cambia-esto` | Clave secreta de Django (obligatoria en producción) |
| `DEBUG` | `False` | Modo depuración |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Hosts permitidos |
| `LANGUAGE_CODE` | `es` | Idioma de la interfaz |
| `TIME_ZONE` | `America/Caracas` | Zona horaria del país de operación |
| `DEFAULT_CURRENCY` | `USD` | Moneda por defecto de los registros y moneda base global |
| `DB_NAME` / `DB_USER` / `DB_PASSWORD` / `DB_HOST` / `DB_PORT` | `sgg_db` … | Conexión a PostgreSQL |
| `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` | `redis://localhost:6379/0` | Redis para Celery |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:3000` | Orígenes permitidos para un frontend externo |

## 5. Seguridad y roles

Cada usuario recibe un rol por empresa (`/api/finance/security/roles/`, gestionado por personal administrador):

| Rol | Lee datos de la empresa | Modifica datos | Ve nómina y bitácora | Configura la empresa |
| --- | :-: | :-: | :-: | :-: |
| Administrador | ✔ | ✔ | ✔ | ✔ |
| Gerente | ✔ | ✔ | ✔ | — |
| Auditor | ✔ | — | ✔ | — |
| Analista | ✔ | — | — | — |
| Solo lectura | ✔ | — | — | — |

- Los listados se filtran automáticamente por las empresas del usuario.
- Un registro de otra empresa responde 404, y crear o mover registros hacia una empresa ajena responde 403.
- Los reportes exigen acceso a la empresa consultada.
- Solo los superusuarios crean empresas nuevas y ven todas las empresas.

## 6. Adaptar a tu país o empresa

Los parámetros que dependen del país se guardan **por empresa** como `TenantSetting` (`/api/tenants/settings/`), sin tocar el código:

**Moneda base** (clave `base_currency`):

```json
"USD"
```

**Nómina** (clave `payroll_config`). Solo hace falta incluir lo que cambia; lo que no se indique toma los valores por defecto, que son las reglas originales de Uganda (PAYE + NSSF):

```json
{
  "income_tax": {
    "code": "income_tax",
    "bands": [[1000, 0], [3000, 10], [null, 20]]
  },
  "social_security": {
    "code": "social_security",
    "employee_rate": 4,
    "employer_rate": 9,
    "monthly_cap": 5000
  },
  "due_day": 15
}
```

- `bands`: tramos progresivos `[límite superior mensual, tasa %]`. El último lleva `null` (sin tope).
- `monthly_cap`: tope de la base de cotización (`null` = sin tope).
- `code`: tipo de obligación que se genera al ejecutar la nómina.
- `due_day`: día del mes siguiente en que vencen las obligaciones.

La configuración se valida al guardarla y la API rechaza los tramos mal formados.

> Nota: la integración de facturación electrónica (EFRIS) es específica de Uganda. Si tu país usa otro sistema, ese conector debe adaptarse.

## 7. Panel gerencial

En `/panel/` (también en `/`), tras iniciar sesión, cada usuario ve el resumen de sus empresas:

- ingresos, gastos y resultado del periodo (desde los asientos contables)
- caja y bancos, cuentas por cobrar e inversiones activas, separados por moneda
- gastos aprobados por categoría
- obligaciones de los próximos 15 días y obligaciones vencidas
- ejecución presupuestaria con barras de progreso
- **alertas**: presupuestos por encima del 90 % o excedidos, obligaciones y facturas vencidas, y gastos pendientes de aprobación

Se puede elegir la empresa y el periodo. Los mismos datos están disponibles en JSON en `/api/finance/reports/dashboard/`.

## 8. API

Documentación interactiva: `/api/docs/` (Swagger), `/api/redoc/` y el esquema en `/api/schema/`.

| Prefijo | Contenido |
| --- | --- |
| `/api/tenants/` | Empresas; `/api/tenants/settings/` para su configuración |
| `/api/finance/accounts/` | Plan de cuentas, asientos y líneas |
| `/api/finance/invoicing/` | Notas de cobro y recordatorios |
| `/api/finance/payments/` | Pagos y créditos de retención |
| `/api/finance/expenses/` | Gastos, reembolsos y lotes |
| `/api/finance/payroll/` | Empleados, asignaciones y nóminas (`runs/run_monthly/`) |
| `/api/finance/statutory/` | Obligaciones fiscales |
| `/api/finance/banking/` | Cuentas, conciliaciones, caja chica y cheques |
| `/api/finance/fx/` | Tipos de cambio |
| `/api/finance/budgets/` | Presupuestos (`approve`, `execution`) y sus líneas |
| `/api/finance/investments/` | Inversiones (`summary`, `portfolio`) y movimientos |
| `/api/finance/security/` | Roles por empresa (`roles/mine/`) |
| `/api/finance/audit/` | Bitácora (solo lectura) |
| `/api/finance/reports/` | Reportes (ver abajo) |

Reportes (todos llevan `tenant_id`):

| Endpoint | Parámetros |
| --- | --- |
| `income-statement/` | `start_date`, `end_date` |
| `balance-sheet/` | `as_of` (por defecto, hoy) |
| `outstanding-invoices/` | — |
| `payroll-summary/` | `year` |
| `dashboard/` | `start_date`, `end_date` (por defecto, del 1 de enero a hoy) |

## 9. Módulos

| App | Modelos principales | Lógica |
| --- | --- | --- |
| `tenants` | Tenant, TenantSetting | `tenants/config.py`: configuración por empresa |
| `finance.security` | UserTenantRole | `permissions.py`: aislamiento y roles |
| `finance.accounts` | Account, JournalEntry, JournalLine | — |
| `finance.invoicing` | FeeNote, FeeNoteReminder | `FeeNoteService` |
| `finance.payments` | FeeNotePayment, WHTCredit | `PaymentService` |
| `finance.expenses` | Expense, ReimbursementRequest, ReimbursementBatch | — |
| `finance.payroll` | EmployeePayrollProfile, EmployeeAllowance, PayrollRun, PayrollLine | `PayrollService`, `config.py` |
| `finance.statutory` | StatutoryObligation | — |
| `finance.banking` | BankAccount, BankReconciliation, PettyCashTransaction, Cheque | — |
| `finance.fx` | ExchangeRate | — |
| `finance.budgets` | Budget, BudgetLine | `services.budget_execution` |
| `finance.investments` | Investment, InvestmentMovement | `services.investment_summary` |
| `finance.reports` | — | `ReportService` |
| `finance.audit` | AuditLog | — |
| `panel` | — | Panel web gerencial |

## 10. Pruebas y calidad

```bash
pytest                                     # toda la suite (pytest-django)
coverage run -m pytest && coverage report  # con cobertura
python manage.py test tests/ --settings=sgg.test_settings  # alternativa sin pytest
flake8 . && isort --check-only .
```

El CI (GitHub Actions) ejecuta en Python 3.11 y 3.12 los chequeos de Django, la detección de migraciones faltantes, las pruebas con cobertura y el lint (flake8 + isort).

## 11. Estructura del proyecto

```text
.
|-- manage.py
|-- sgg/                 # configuración del proyecto (settings, urls, celery)
|-- tenants/             # empresas y configuración por empresa
|-- finance/
|   |-- accounts/  invoicing/  payments/  expenses/  payroll/
|   |-- statutory/  banking/  fx/  audit/  reports/
|   `-- security/  budgets/  investments/
|-- panel/               # panel web
|-- templates/           # plantillas HTML (panel y login)
`-- tests/
```

## 12. Notas de operación

- Usa PostgreSQL en ejecución; las pruebas usan SQLite en memoria.
- En producción: `DEBUG=False`, una `SECRET_KEY` propia, y `ALLOWED_HOSTS` y CORS explícitos.
- Todo modelo nuevo con datos de empresa debe usar `TenantScopedMixin` en su vista (indicando `tenant_path` si la empresa se alcanza a través de un objeto padre).
- Los importes de distintas monedas nunca se suman entre sí en los reportes.

## 13. Licencia

MIT. Consulta [LICENSE](LICENSE). Se conserva el aviso de copyright del proyecto original del que parte SGG.
