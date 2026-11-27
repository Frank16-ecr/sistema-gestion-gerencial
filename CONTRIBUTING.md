# Contributing to SGG - Sistema de Gestión Gerencial

Thank you for taking the time to contribute! The following guidelines help us keep the project consistent and easy to collaborate on.

---

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Branching Strategy](#branching-strategy)
- [Commit Messages](#commit-messages)
- [Pull Requests](#pull-requests)
- [Coding Standards](#coding-standards)
- [Running Tests](#running-tests)
- [Reporting Bugs](#reporting-bugs)
- [Requesting Features](#requesting-features)

---

## Code of Conduct

Be respectful and constructive in all interactions.  
Harassment of any kind will not be tolerated.

---

## Getting Started

1. **Fork** the repository and clone your fork locally.
2. Set up the development environment:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env   # fill in your local credentials
   python manage.py migrate
   ```

3. Create a branch for your change (see [Branching Strategy](#branching-strategy)).
4. Make your changes, write/update tests, and ensure everything passes.
5. Open a pull request.

---

## Branching Strategy

| Branch | Purpose |
|--------|---------|
| `main` | Production-ready code |
| `develop` | Integration branch for in-progress work |
| `feature/<name>` | New features |
| `fix/<name>` | Bug fixes |
| `chore/<name>` | Refactors, dependency updates, documentation |

Always branch off `develop` for new work.

---

## Commit Messages

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <short summary>

[optional body]
[optional footer]
```

**Types:** `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

**Examples:**

```
feat(invoicing): auto-generate fee note on claim close
fix(payroll): correct NSSF employer contribution rate
docs: update README quickstart for Docker
```

---

## Pull Requests

- Target `develop` (not `main`).
- Include a clear description of **what** changed and **why**.
- Reference any related issue: `Closes #123`.
- All CI checks must pass before merging.
- At least one approving review is required.

---

## Coding Standards

- **Python style:** PEP 8 via `flake8` (config in `setup.cfg`).
- **Import ordering:** `isort` (config in `setup.cfg`).
- **Business logic:** belongs in `services.py`, not in views or signals.
- **Tenant isolation:** every queryset that touches finance data **must** filter by `tenant`.
- **Atomic transactions:** wrap every multi-step financial operation in `django.db.transaction.atomic()`.
- **No hard deletes:** use `is_void` / `voided_at` / `void_reason` on financial records.

Run the linters:

```bash
make lint        # flake8
make isort-check # isort
```

Auto-fix imports:

```bash
make isort
```

---

## Running Tests

Tests use an in-memory SQLite database — no PostgreSQL or Redis required.

```bash
make test
# or directly:
python manage.py test tests/ --settings=sgg.test_settings
```

---

## Reporting Bugs

Open a GitHub Issue with:

1. A clear, descriptive title.
2. Steps to reproduce.
3. Expected vs actual behaviour.
4. Django/Python versions and OS.
5. Relevant stack trace or log output.

---

## Requesting Features

Open a GitHub Issue labelled `enhancement` describing:

1. The problem you need to solve.
2. Your proposed solution or API.
3. Any alternatives you considered.
