# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added
- Initial implementation of the Zelani Finance Module

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
