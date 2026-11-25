# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Cambiado
- El proyecto pasa a llamarse **SGG · Sistema de Gestión Gerencial**: el paquete `zelani` ahora es `sgg`, junto con la base de datos por defecto (`sgg_db`), el usuario de Docker, Celery, el CI y la documentación. El README está en español y sus badges apuntan a `Frank16-ecr/sistema-gestion-gerencial`.
- Idioma por defecto en español; `LANGUAGE_CODE`, `TIME_ZONE` y `DEFAULT_CURRENCY` se configuran por variables de entorno.
- Las monedas por defecto de los modelos salen de `DEFAULT_CURRENCY`, y la moneda base puede definirse por empresa (`TenantSetting` con clave `base_currency`).
- La nómina admite tramos de impuesto, seguridad social (con tope), códigos de obligación y día de vencimiento configurables por empresa (`payroll_config`). Por defecto se mantienen las reglas de Uganda.
- Las categorías de gasto y los tipos de obligación tienen etiquetas en español.
- La lógica de ejecución presupuestaria y de portafolio de inversiones se movió a `services.py` para poder reutilizarla.

### Añadido
- Reportes nuevos: **balance general** (`balance-sheet/`) y **resumen gerencial** (`dashboard/`) con alertas.
- **Panel web** en `/panel/` con inicio de sesión, selección de empresa y periodo, modo claro y oscuro y diseño adaptable a móvil.
- Configuración de pytest (`pytest-django`) y de cobertura; nuevos objetivos `make pytest`, `make coverage` e `install-dev`.
- El CI comprueba que no falten migraciones y mide la cobertura.
- 41 pruebas nuevas (85 en total): aislamiento entre empresas, reportes, nómina configurable y panel.

### Corregido
- **Seguridad**: los módulos originales (contabilidad, facturación, pagos, gastos, nómina, obligaciones, bancos, divisas, auditoría, empresas y reportes) solo exigían inicio de sesión, así que cualquier usuario podía leer y modificar datos de todas las empresas. Ahora todos filtran por empresa y por rol. Los salarios y la bitácora quedan restringidos a administración, gerencia y auditoría.
- `/api/tenants/settings/` era inalcanzable: la ruta de empresas, con prefijo vacío, la capturaba antes.
- Los listados paginados no tenían un orden fijo (`UnorderedObjectListWarning`), por lo que una página podía repetir u omitir registros.
- `run_monthly` y los reportes fallaban con error 500 ante parámetros inválidos; ahora responden 400.
- El contenedor `beat` de docker-compose usaba `django_celery_beat`, que no está instalado.
- El job de lint del CI fallaba (líneas largas, imports sin usar y orden de imports).

---

## [1.0.0] - 2025-03-11

### Added

#### Project foundation
- Django 4.2 project with PostgreSQL backend, Celery + Redis task queue, and DRF API
- Multi-tenant architecture with `Tenant` and `TenantSetting` models
- `setup.cfg` for flake8 and isort configuration
- `Makefile` with common developer commands
- `Dockerfile` (multi-stage) and `docker-compose.yml` for local development
- GitHub Actions CI workflow running tests on Python 3.11 and 3.12

#### `finance/accounts` — Chart of accounts & bookkeeping engine
- `Account` model with hierarchical parent/child support and five categories (asset, liability, equity, income, expense)
- `JournalEntry` and `JournalLine` models supporting double-entry bookkeeping, multi-currency lines, and void workflow

#### `finance/invoicing` — Fee notes
- `FeeNote` model with full lifecycle status (draft → EFRIS submitted → stamped → sent → partial/paid → overdue → void)
- `FeeNoteReminder` model for tracking automated reminder emails
- `FeeNoteService`: generate from claim data, submit to EFRIS, send to insurer, void, update overdue statuses

#### `finance/payments` — Payment recording
- `FeeNotePayment` model supporting multi-currency payments with FX gain/loss, WHT deductions, proof-of-payment upload, and EFRIS acknowledgement reference
- `WHTCredit` model for tracking withholding-tax credits
- `PaymentService`: record payment, calculate FX gain/loss, create WHT credit, update invoice balance and status

#### `finance/expenses` — Expenses & reimbursements
- `Expense` model for general business expenses (rent, fuel, audit fees, etc.) with approval workflow
- `ReimbursementRequest` model for claim-linked staff reimbursements with approval and batching workflow
- `ReimbursementBatch` model for weekly reimbursement batch payments

#### `finance/payroll` — Payroll
- `EmployeePayrollProfile` and `EmployeeAllowance` models
- `PayrollRun` and `PayrollLine` models with draft → approved → paid workflow
- `PayrollService`: Uganda PAYE tax-band calculations, employee/employer NSSF (5%/10%), monthly payroll run with automatic statutory obligation creation

#### `finance/statutory` — Statutory obligations
- `StatutoryObligation` model tracking PAYE, NSSF, VAT, and provisional income-tax due dates, amounts, and filing/payment status

#### `finance/banking` — Banking & cash
- `BankAccount` model (current, savings, petty cash)
- `BankReconciliation` model with monthly lock support
- `PettyCashTransaction` model for withdrawals and top-ups
- `Cheque` model for receipt and issued cheques with bounced-cheque support

#### `finance/fx` — Foreign exchange
- `ExchangeRate` model with manual/automatic source, historical rate storage, and unique constraint per currency pair per day

#### `finance/audit` — Immutable audit trail
- `AuditLog` model recording every create/update/void/approve/EFRIS action with before/after JSON values

#### `finance/reports` — Financial reports
- Income statement (P&L) view
- Outstanding invoices (aged receivables) view
- Payroll summary view

#### API & admin
- DRF ViewSets and serializers for all models
- Django admin registration for all models with list_display, search_fields, and list_filter
- OpenAPI schema via drf-spectacular (Swagger UI at `/api/docs/`, ReDoc at `/api/redoc/`)

#### Tests
- 21 passing unit tests covering model creation and key service methods

[Unreleased]: https://github.com/zelanitech/Zelani-Finance-Module/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/zelanitech/Zelani-Finance-Module/releases/tag/v1.0.0
