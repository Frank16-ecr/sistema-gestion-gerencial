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
- **Nómina mensual o quincenal** con impuestos y seguridad social **configurables por empresa**. Por defecto aplica las reglas venezolanas: ISLR por AR-I, IVSS y RPE por lunes, FAOV, INCES y pensiones.
- **Facturación venezolana**: RIF, número de factura y número de control consecutivos, IVA general, reducido y de lujo, exentos, equivalente en Bs a tasa BCV, IGTF sobre pagos en divisas, retenciones de IVA, notas de crédito y débito, anulación y libro de ventas (exportable a Excel).
- **Tasa BCV automática**: descarga diaria de la tasa oficial del Banco Central de Venezuela.
- **Asientos contables automáticos** de facturas, cobros (con diferencial cambiario), retenciones y nómina, sobre un plan de cuentas venezolano básico.
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
| `DEFAULT_CURRENCY` | `VES` | Moneda por defecto de los registros y moneda base global |
| `PAYROLL_COUNTRY` | `VE` | Preset de nómina para las empresas sin configuración propia (`VE` o `UG`) |
| `DB_NAME` / `DB_USER` / `DB_PASSWORD` / `DB_HOST` / `DB_PORT` | `sgg_db` … | Conexión a PostgreSQL |
| `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` | `redis://localhost:6379/0` | Redis para Celery |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:3000` | Orígenes permitidos para un frontend externo |
| `BCV_URL` | `https://www.bcv.org.ve/` | Página de la que se lee la tasa oficial |
| `BCV_CA_BUNDLE` | `/etc/ssl/bcv-chain.pem` | Bundle de certificados propio, por si el certificado del BCV da error (TLS nunca se desactiva) |

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

El sistema viene configurado para **Venezuela**: zona horaria `America/Caracas`, moneda base en bolívares (`VES`) y nómina venezolana. Cada empresa puede ajustar estos valores con `TenantSetting` (`/api/tenants/settings/`) sin tocar el código.

### Configuración rápida de una empresa

```bash
python manage.py configurar_pais mi-empresa VE --riesgo medio --salario-minimo 130
```

En Venezuela este comando también crea el plan de cuentas básico (usa `--sin-plan-cuentas` para omitirlo). Para crearlo por separado: `python manage.py crear_plan_cuentas mi-empresa`.

| Opción | Para qué sirve |
| --- | --- |
| `--riesgo bajo/medio/alto` | Aporte patronal del IVSS: 9 %, 10 % u 11 % |
| `--salario-minimo` | Salario mínimo mensual, que fija los topes del IVSS y del RPE |
| `--piso-pensiones` | Base mínima por trabajador de la contribución de pensiones (ingreso mínimo integral indexado) |
| `--moneda USD` | Moneda base distinta de VES |

### Nómina venezolana (preset `VE`)

| Concepto | Trabajador | Patrono | Base | Tope |
| --- | --- | --- | --- | --- |
| ISLR | % del AR-I de cada trabajador | — | salario + asignaciones gravables | — |
| IVSS | 4 % | 9 % (riesgo bajo, configurable) | salario semanal × lunes del periodo | 5 salarios mínimos |
| RPE (paro forzoso) | 0,5 % | 2 % | salario semanal × lunes del periodo | 10 salarios mínimos |
| FAOV | 1 % | 2 % | salario + asignaciones | — |
| INCES | — | 2 % | salario + asignaciones | — |
| Protección de Pensiones | — | 9 % | salario + bonificaciones | piso configurable |

- El porcentaje de ISLR de cada trabajador se guarda en su ficha, en el campo `income_tax_rate`, según su formulario AR-I.
- Cada aporte genera su propia obligación (`islr`, `ivss`, `rpe`, `faov`, `inces`, `pension`) con vencimiento el día 15 del mes siguiente. Ese día se puede cambiar en general o por aporte.
- El detalle por aporte queda en cada línea de nómina (`contributions`) y los totales en la nómina (`contributions_summary`).
- **IVSS y RPE se cotizan por semanas**: el salario mensual se convierte a semanal (× 12 / 52) y se multiplica por los lunes del periodo. Un mes con 5 lunes cotiza más que uno con 4.
- **Quincenas**: `POST /api/finance/payroll/runs/run_monthly/` con `period` igual a `q1` (días 1 a 15) o `q2` (día 16 a fin de mes). Cada quincena paga la mitad del salario y de las asignaciones. Las obligaciones del mes suman ambas quincenas. Un mes se procesa o como mensual o por quincenas, nunca de las dos formas.
- **Aprobación**: `POST /api/finance/payroll/runs/{id}/approve/` aprueba la nómina y registra su asiento (sueldos y aportes patronales contra sueldos por pagar, ISLR retenido y aportes por pagar). El estado y los totales solo cambian con estas acciones.
- Solo entran en la nómina quienes ya habían ingresado y no habían egresado en el periodo.

> ⚠️ Estas tasas y topes son **referencias de 2026** y pueden cambiar por Gaceta Oficial. El salario mínimo y el piso de la contribución de pensiones en particular deben confirmarse con tu contador antes de procesar una nómina real. Ninguna cifra está fija en el código: todas se ajustan en la configuración.

### Configuración avanzada (clave `payroll_config`)

Basta con indicar lo que cambia respecto del preset del país:

```json
{
  "country": "VE",
  "minimum_wage": 130,
  "due_day": 15,
  "contributions": [
    {"code": "ivss", "name": "Seguro Social", "employee_rate": 4, "employer_rate": 10,
     "base": "salary", "cap_minimum_wages": 5},
    {"code": "pension", "name": "Pensiones", "employee_rate": 0, "employer_rate": 9,
     "base": "total", "floor_amount": 5000, "due_day": 5}
  ]
}
```

- `contributions` reemplaza la lista completa de aportes. Cada aporte acepta `base` (`salary` o `total`), `cap_minimum_wages`, `cap_amount`, `floor_amount` y `due_day`.
- `income_tax.method` puede ser `employee_rate` (porcentaje por trabajador) o `bands`, con tramos progresivos `[[límite, tasa %], …, [null, tasa %]]`.
- La moneda base se define con la clave `base_currency` (por ejemplo, `"VES"` o `"USD"`).
- También existe el preset `UG` (Uganda, PAYE + NSSF), que son las reglas originales del proyecto.

La configuración se valida al guardarla, y la API rechaza los valores inválidos.

### Tasa BCV

- **Automática**: Celery Beat la descarga de lunes a viernes a las 6:15 pm (hora de Caracas) y la guarda con su *fecha valor* para cada empresa que contabiliza en bolívares. Si falla, reintenta cada 30 minutos.
- **Manual**: `python manage.py actualizar_tasa_bcv`. Sin conexión, acepta la portada guardada: `--archivo portada.html`.
- Facturas, cobros e IGTF usan la última tasa publicada en o antes de su fecha. Si no hay tasa, la operación se rechaza con un mensaje claro.

### Facturación (`/api/finance/sales/`)

1. **Datos fiscales**: registra en `taxpayer-profiles/` el RIF, la razón social y el domicilio fiscal de la empresa, y si es contribuyente especial o agente de percepción del IGTF.
2. **Clientes** (`customers/`): RIF validado (`J-12345678-9`) y porcentaje de retención de IVA (0, 75 o 100 %) si el cliente es contribuyente especial.
3. **Factura en borrador** (`invoices/`): líneas con alícuota `general` (16 %), `reduced` (8 %), `luxury` (16 % + 15 % adicional) o `exempt`, en VES o en divisas.
4. **Emisión** (`invoices/{id}/issue/`): asigna el número de factura y el número de control (00-XXXXXXXX), ambos consecutivos y sin saltos; fija la tasa BCV; congela los datos del cliente; registra el asiento (CxC contra ventas e IVA débito fiscal) y actualiza el IVA del mes.
5. **Cobros** (`invoices/{id}/pay/`): en cualquier moneda, a la tasa BCV del día. Si el pago es en divisas y la empresa es agente de percepción, se calcula el **IGTF del 3 %**. El **diferencial cambiario** entre la tasa de emisión y la del pago va a ganancia o pérdida.
6. **Retención de IVA** (`invoices/{id}/withholding/`): comprobante de 14 dígitos del cliente especial (75 % o 100 % del IVA).
7. **Correcciones**: los documentos emitidos no se editan ni se borran. Se corrigen con **notas de crédito o débito** (`doc_type` igual a `credit_note` o `debit_note`, con `related_invoice`) o se **anulan** (`void/`, con motivo), lo que conserva su número y revierte el asiento.
8. **Libro de ventas**: `sales-book/?tenant_id=…&year=…&month=…`, en bolívares, con las notas de crédito en negativo y las anuladas marcadas. Con `&export=csv` se descarga para Excel.

Las obligaciones **IVA** (débito fiscal del libro menos retenciones recibidas) e **IGTF** (percibido en los cobros) se generan solas para cada mes. Una obligación ya declarada o pagada no se modifica.

> Alcance: no hay libro de compras, así que el crédito fiscal de compras se descuenta al hacer la declaración. La numeración se gestiona en el sistema; para facturación digital homologada por el SENIAT (Providencia SNAT/2024/000102) hay que integrar una imprenta digital autorizada que asigne los números de control.

> El módulo `invoicing` (notas de cobro con EFRIS) viene del proyecto original y es de Uganda. Para Venezuela usa `sales`.

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
| `/api/finance/sales/` | Facturación venezolana: datos fiscales, clientes, facturas (`issue`, `pay`, `withholding`, `void`), cobros, retenciones y `sales-book/` |
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
| `finance.accounts` | Account, JournalEntry, JournalLine | `services.py`: asientos automáticos y plan de cuentas |
| `finance.invoicing` | FeeNote, FeeNoteReminder | `FeeNoteService` |
| `finance.payments` | FeeNotePayment, WHTCredit | `PaymentService` |
| `finance.expenses` | Expense, ReimbursementRequest, ReimbursementBatch | — |
| `finance.payroll` | EmployeePayrollProfile, EmployeeAllowance, PayrollRun, PayrollLine | `PayrollService`, `config.py` |
| `finance.statutory` | StatutoryObligation | — |
| `finance.banking` | BankAccount, BankReconciliation, PettyCashTransaction, Cheque | — |
| `finance.fx` | ExchangeRate | `services.py`: tasa BCV y `get_rate` |
| `finance.budgets` | Budget, BudgetLine | `services.budget_execution` |
| `finance.investments` | Investment, InvestmentMovement | `services.investment_summary` |
| `finance.reports` | — | `ReportService` |
| `finance.sales` | TaxpayerProfile, Customer, Invoice, InvoiceLine, InvoicePayment, VatWithholding | `services.py`: emisión, cobros, IGTF, libro de ventas |
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
|   `-- security/  budgets/  investments/  sales/
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
