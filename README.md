# Zelani Finance Module

[![CI](https://github.com/zelanitech/Zelani-Finance-Module/actions/workflows/ci.yml/badge.svg)](https://github.com/zelanitech/Zelani-Finance-Module/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue)](https://www.python.org/downloads/)
[![Django](https://img.shields.io/badge/django-4.2-green)](https://www.djangoproject.com/)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)

A production-oriented, multi-tenant finance backend for Zelani. It centralizes invoicing, collections, expenses, payroll, statutory obligations, banking, FX, accounting, and audit trails in one Django REST API.

## Table of Contents

- [1. Business Context](#1-business-context)
- [2. Core Capabilities](#2-core-capabilities)
- [3. Technology Stack](#3-technology-stack)
- [4. System Architecture](#4-system-architecture)
- [5. Domain Modules](#5-domain-modules)
- [6. Request Lifecycle](#6-request-lifecycle)
- [7. Getting Started](#7-getting-started)
- [8. Configuration](#8-configuration)
- [9. API Surface](#9-api-surface)
- [10. Data and Accounting Flow](#10-data-and-accounting-flow)
- [11. Testing and Quality](#11-testing-and-quality)
- [12. Project Layout](#12-project-layout)
- [13. Operations Notes](#13-operations-notes)
- [14. Contribution Guide](#14-contribution-guide)
- [15. License](#15-license)

## 1. Business Context

Insurance and claims operations usually split financial processes across disconnected tools. This module keeps everything in one place and links transactions to tenants and business events.

Typical outcomes:

- Faster fee note generation and insurer follow-up.
- Better visibility into receivables, payroll costs, and liabilities.
- Cleaner month-end close through structured journals and reports.
- Lower audit risk via immutable action history.

## 2. Core Capabilities

- Multi-tenant data model using tenant-aware entities.
- Double-entry accounting structures via accounts and journal entities.
- Fee note lifecycle for invoice issuance and reminders.
- Payment capture with withholding tax credit tracking.
- Expense and reimbursement workflows.
- Payroll computation and payroll line breakdowns.
- Statutory obligation tracking (due dates, statuses, amounts).
- Bank and petty cash records with reconciliation support.
- FX rates and multi-currency support.
- Reporting endpoints for income statement, receivables, and payroll summaries.
- Immutable audit records for key actions.

## 3. Technology Stack

- Python 3.11 and 3.12
- Django 4.2
- Django REST Framework
- PostgreSQL (primary runtime database)
- Celery + Redis (asynchronous jobs and scheduling)
- drf-spectacular (OpenAPI schema + Swagger/ReDoc)
- Docker + Docker Compose (local and CI-friendly packaging)

## 4. System Architecture

```text
Client Apps / Admin UI
          |
          v
   Django REST API (zelani.urls)
          |
          +--> tenants app (tenant registry and configuration)
          +--> finance domain apps
          |      - accounts
          |      - invoicing
          |      - payments
          |      - expenses
          |      - payroll
          |      - statutory
          |      - banking
          |      - fx
          |      - audit
          |      - reports
          |
          +--> PostgreSQL (persistent data)
          +--> Redis (broker/backend)
                    |
                    v
                  Celery worker/beat
```

The project follows modular Django app boundaries. Every finance area has models, serializers, views, and URLs, with business logic consolidated in service modules where workflows are non-trivial.

## 5. Domain Modules

### Tenancy

- App: tenants
- Key models:
  - Tenant
  - TenantSetting
- Responsibility: tenant registry and tenant-level settings used across all finance apps.

### Accounts (Double-entry foundation)

- App: finance.accounts
- Key models:
  - Account
  - JournalEntry
  - JournalLine
- Responsibility: chart-of-accounts structures and general journal lines posted by financial events.

### Invoicing

- App: finance.invoicing
- Key models:
  - FeeNote
  - FeeNoteReminder
- Service: FeeNoteService
- Responsibility: issue fee notes, track status and reminders.

### Payments

- App: finance.payments
- Key models:
  - FeeNotePayment
  - WHTCredit
- Service: PaymentService
- Responsibility: register incoming payments and withholding tax credits.

### Expenses

- App: finance.expenses
- Key models:
  - Expense
  - ReimbursementBatch
  - ReimbursementRequest
- Responsibility: expense capture and reimbursement management.

### Payroll

- App: finance.payroll
- Key models:
  - EmployeePayrollProfile
  - EmployeeAllowance
  - PayrollRun
  - PayrollLine
- Service: PayrollService
- Responsibility: payroll run computation and employee-level line items.

### Statutory

- App: finance.statutory
- Key model:
  - StatutoryObligation
- Responsibility: track statutory payable obligations and due dates.

### Banking

- App: finance.banking
- Key models:
  - BankAccount
  - BankReconciliation
  - PettyCashTransaction
  - Cheque
- Responsibility: bank operations and reconciliation records.

### FX

- App: finance.fx
- Key model:
  - ExchangeRate
- Responsibility: exchange rate storage and conversion support.

### Audit

- App: finance.audit
- Key model:
  - AuditLog
- Responsibility: append-only operational traceability.

### Reports

- App: finance.reports
- Endpoints expose:
  - Income statement data
  - Outstanding invoices/receivables
  - Payroll summary metrics

## 6. Request Lifecycle

1. Client authenticates and calls API endpoint.
2. DRF view validates input with serializer.
3. Business service executes workflow where applicable.
4. Domain models are saved in PostgreSQL.
5. Related financial or audit records are generated.
6. API returns normalized response payload.

## 7. Getting Started

### Prerequisites

- Python 3.11 or 3.12
- PostgreSQL 14+
- Redis 7+
- Docker Desktop or Docker Engine (optional, recommended)

### Option A: Docker (recommended)

```bash
git clone https://github.com/zelanitech/Zelani-Finance-Module.git
cd Zelani-Finance-Module
cp .env.example .env
docker compose up --build
```

Create an admin account:

```bash
docker compose exec web python manage.py createsuperuser
```

### Option B: Local virtualenv

```bash
git clone https://github.com/zelanitech/Zelani-Finance-Module.git
cd Zelani-Finance-Module

python3 -m venv .venv
source .venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt

cp .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Start worker processes in separate terminals:

```bash
celery -A zelani worker -l info
celery -A zelani beat -l info
```

### Useful Make targets

```bash
make help
make install
make migrate
make run
make test
make lint
make docker-up
```

## 8. Configuration

Create .env from .env.example and set the following values:

| Variable | Required | Example | Purpose |
| --- | --- | --- | --- |
| SECRET_KEY | Yes | change-me | Django secret |
| DEBUG | No | True | Django debug mode |
| ALLOWED_HOSTS | No | localhost,127.0.0.1 | Allowed hosts list |
| DB_NAME | Yes | zelani_db | PostgreSQL database |
| DB_USER | Yes | postgres | PostgreSQL user |
| DB_PASSWORD | Yes | password | PostgreSQL password |
| DB_HOST | Yes | localhost | PostgreSQL host |
| DB_PORT | No | 5432 | PostgreSQL port |
| CELERY_BROKER_URL | Yes | redis://localhost:6379/0 | Celery broker |
| CELERY_RESULT_BACKEND | Yes | redis://localhost:6379/0 | Celery result backend |
| CORS_ALLOWED_ORIGINS | No | http://localhost:3000 | Comma-separated origins |

## 9. API Surface

### Documentation endpoints

- GET /api/schema/
- GET /api/docs/
- GET /api/redoc/

### Resource endpoints

- /api/tenants/
- /api/finance/accounts/
- /api/finance/invoicing/
- /api/finance/payments/
- /api/finance/expenses/
- /api/finance/payroll/
- /api/finance/statutory/
- /api/finance/banking/
- /api/finance/fx/
- /api/finance/audit/
- /api/finance/reports/

All endpoints are authenticated by default through DRF settings.

## 10. Data and Accounting Flow

Examples of end-to-end flow:

- Invoice flow:
  1. Fee note created.
  2. Receivable impact recorded in accounting layer.
  3. Reminder records may be generated.

- Collection flow:
  1. Payment posted against fee note.
  2. Outstanding balance is reduced.
  3. WHT credits are tracked when supplied.

- Payroll flow:
  1. Payroll run created.
  2. Payroll lines generated per employee.
  3. Statutory obligations and expense implications become reportable.

## 11. Testing and Quality

### Run checks and tests

```bash
python manage.py check --settings=zelani.test_settings
python manage.py test tests/ --settings=zelani.test_settings --verbosity=2
```

### Linting

```bash
flake8 .
isort --check-only --diff .
```

The CI workflow runs tests on Python 3.11 and 3.12 and executes lint checks in a dedicated job.

## 12. Project Layout

```text
.
|-- manage.py
|-- requirements.txt
|-- requirements-dev.txt
|-- Dockerfile
|-- docker-compose.yml
|-- Makefile
|-- finance/
|   |-- accounts/
|   |-- invoicing/
|   |-- payments/
|   |-- expenses/
|   |-- payroll/
|   |-- statutory/
|   |-- banking/
|   |-- fx/
|   |-- audit/
|   `-- reports/
|-- tenants/
|-- tests/
`-- zelani/
```

## 13. Operations Notes

- Use PostgreSQL in runtime environments. The test settings use SQLite for fast CI test execution.
- Keep tenant boundaries strict in all future model additions.
- Avoid committing generated runtime artifacts such as __pycache__ and .pyc files.
- For production hardening: set DEBUG=False, rotate secrets, and configure ALLOWED_HOSTS/CORS explicitly.

## 14. Contribution Guide

Please read CONTRIBUTING.md before opening issues or pull requests.

## 15. License

MIT License. See LICENSE for details.
