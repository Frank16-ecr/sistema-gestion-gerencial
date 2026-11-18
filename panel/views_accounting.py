"""Contabilidad: plan de cuentas, asientos y reportes."""

from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Sum
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from finance.accounts.models import Account, JournalEntry
from finance.reports.services import ReportService

from .common import context, require_write, scoped_object
from .forms_ops import AccountForm, DateRangeForm, JournalEntryForm, JournalLineFormSet
from .ui import act, cell, chart, es, f, fdate, fmt, kpi, money_cell, status_cell, table

PAGE = 'panel/generic_page.html'
FORM = 'panel/generic_form.html'
MONTHS = [
    'enero',
    'febrero',
    'marzo',
    'abril',
    'mayo',
    'junio',
    'julio',
    'agosto',
    'septiembre',
    'octubre',
    'noviembre',
    'diciembre',
]
CATEGORY_ORDER = ['asset', 'liability', 'equity', 'income', 'expense']


def _url(name, *args):
    return reverse(f'panel:{name}', args=args)


# --------------------------------------------------------------------------- plan de cuentas


@login_required
def account_list(request):
    ctx = context(request, section='coa', page_title='Plan de cuentas')
    tenant = ctx['tenant']
    accounts = Account.objects.filter(tenant=tenant).select_related('parent').order_by('code')
    category = request.GET.get('category', '')
    shown = accounts.filter(category=category) if category else accounts
    counts = {row['category']: row['n'] for row in accounts.values('category').annotate(n=Count('id'))}
    rows = [
        {
            'cells': [
                cell(a.code, href=_url('account-edit', a.pk) if ctx['can_write'] else None, sort=a.code),
                cell(a.name, sub=f'Depende de {a.parent.code}' if a.parent else None),
                cell(es(a.category)),
                status_cell('open' if a.is_active else 'cancelled', 'Activa' if a.is_active else 'Inactiva'),
            ]
        }
        for a in shown
    ]
    present = [c for c in CATEGORY_ORDER if counts.get(c)]
    charts = (
        [
            chart(
                'chart-coa',
                'Cuentas por categoría',
                'doughnut',
                [es(c) for c in present],
                [
                    {
                        'data': [counts[c] for c in present],
                        'color': ['navy', 'fuchsia', 'sky', 'green', 'amber'][: len(present)],
                    }
                ],
            )
        ]
        if present
        else []
    )
    ctx.update(
        page_sub=tenant.name,
        charts=charts,
        page_actions=(
            [act('+ Nueva cuenta', _url('account-create'), style='primary', method='get')] if ctx['can_write'] else []
        ),
        filters=[
            {
                'name': 'category',
                'label': 'Categoría',
                'current': category,
                'choices': [(c, es(c)) for c in CATEGORY_ORDER],
            }
        ],
        filters_active=bool(category),
        tables=[
            table(
                ['Código', 'Nombre', 'Categoría', 'Estado'], rows, table_id='coa', empty='Aún no hay cuentas contables.'
            )
        ],
    )
    return render(request, PAGE, ctx)


def _account_form(request, account, creating):
    form = AccountForm(request.POST or None, instance=account, tenant=account.tenant)
    if request.method == 'POST' and form.is_valid():
        saved = form.save(commit=False)
        saved.tenant = account.tenant
        saved.save()
        messages.success(request, 'Cuenta creada.' if creating else 'Cuenta actualizada.')
        return redirect('panel:chart-of-accounts')
    ctx = context(
        request,
        obj_tenant=account.tenant,
        section='coa',
        form=form,
        back_url=_url('chart-of-accounts'),
        page_title='Nueva cuenta contable' if creating else f'Editar {account.code}',
        page_sub=account.tenant.name,
        submit_label='Crear cuenta' if creating else 'Guardar cambios',
        wide_fields=['name'],
    )
    return render(request, FORM, ctx)


@login_required
def account_create(request):
    ctx = context(request)
    require_write(request, ctx['tenant'])
    return _account_form(request, Account(tenant=ctx['tenant']), creating=True)


@login_required
def account_edit(request, pk):
    account = scoped_object(request, Account.objects.select_related('tenant'), pk)
    require_write(request, account.tenant)
    return _account_form(request, account, creating=False)


# --------------------------------------------------------------------------- asientos


@login_required
def journal_list(request):
    ctx = context(request, section='journal', page_title='Asientos contables')
    tenant = ctx['tenant']
    entries = (
        JournalEntry.objects.filter(tenant=tenant)
        .annotate(debit=Sum('lines__debit_amount'), n=Count('lines'))
        .order_by('-entry_date', '-id')
    )
    rows = [
        {
            'cells': [
                cell(fdate(e.entry_date), href=_url('journal-detail', e.pk), sort=str(e.entry_date)),
                cell(e.reference or '—', sub=(e.description[:70] or None)),
                cell(e.n),
                money_cell(e.debit or 0),
                status_cell(
                    'void' if e.is_void else ('locked' if e.created_by_system else 'open'),
                    'Anulado' if e.is_void else ('Automático' if e.created_by_system else 'Manual'),
                ),
            ]
        }
        for e in entries[:300]
    ]
    ctx.update(
        page_sub=tenant.name,
        page_actions=(
            [act('+ Nuevo asiento', _url('journal-create'), style='primary', method='get')] if ctx['can_write'] else []
        ),
        tables=[
            table(
                ['Fecha', 'Referencia', 'Líneas', ('Total', {'num': True}), 'Origen'],
                rows,
                table_id='journal',
                empty='Aún no hay asientos.',
                sub='Se muestran los 300 más recientes.',
            )
        ],
    )
    return render(request, PAGE, ctx)


@login_required
def journal_create(request):
    ctx = context(request)
    tenant = ctx['tenant']
    require_write(request, tenant)
    entry = JournalEntry(tenant=tenant, created_by=request.user)
    form = JournalEntryForm(request.POST or None, instance=entry, tenant=tenant)
    formset = JournalLineFormSet(request.POST or None, instance=entry, form_kwargs={'tenant': tenant})
    if request.method == 'POST' and form.is_valid() and formset.is_valid():
        with transaction.atomic():
            saved = form.save()
            for line_form in formset.forms:
                if not line_form.has_changed() or not line_form.cleaned_data:
                    continue
                line = line_form.save(commit=False)
                line.journal_entry, line.tenant = saved, tenant
                line.save()
        messages.success(request, 'Asiento registrado.')
        return redirect('panel:journal-detail', pk=saved.pk)
    ctx.update(form=form, formset=formset, has_accounts=Account.objects.filter(tenant=tenant, is_active=True).exists())
    ctx['section'] = 'journal'
    return render(request, 'panel/journal_form.html', ctx)


@login_required
def journal_detail(request, pk):
    entry = scoped_object(request, JournalEntry.objects.select_related('tenant', 'created_by'), pk)
    ctx = context(request, obj_tenant=entry.tenant, section='journal')
    lines = list(entry.lines.select_related('account').order_by('id'))
    rows = [
        {
            'cells': [
                cell(line.account.code, sub=line.account.name),
                cell(line.description or '—'),
                money_cell(line.debit_amount or None),
                money_cell(line.credit_amount or None),
            ]
        }
        for line in lines
    ]
    debit = sum((line.debit_amount for line in lines), Decimal('0'))
    credit = sum((line.credit_amount for line in lines), Decimal('0'))
    actions = []
    if ctx['can_write'] and not entry.is_void and not entry.created_by_system:
        actions = [
            act(
                'Anular asiento',
                _url('journal-void', entry.pk),
                style='danger',
                prompt='Motivo de la anulación (obligatorio)',
            )
        ]
    facts = [
        ('Fecha', fdate(entry.entry_date)),
        ('Referencia', entry.reference),
        ('Descripción', entry.description),
        ('Origen', 'Automático (sistema)' if entry.created_by_system else f'Manual · {entry.created_by or "—"}'),
    ]
    if entry.is_void:
        facts.append(('Anulado', f'{entry.void_reason} ({fdate(entry.voided_at)})'))
    ctx.update(
        back_url=_url('journal'),
        back_label='Asientos contables',
        page_title=f'Asiento {entry.reference or "#" + str(entry.pk)}',
        badges=[{'text': 'Anulado', 'cls': 'bad'}] if entry.is_void else [],
        page_sub=entry.tenant.name,
        page_actions=actions,
        facts=facts,
        kpis=[kpi('Total Debe', fmt(debit)), kpi('Total Haber', fmt(credit), variant='navy')],
        tables=[
            table(
                ['Cuenta', 'Detalle', ('Debe', {'num': True}), ('Haber', {'num': True})],
                rows,
                table_id='entry-lines',
                searchable=False,
            )
        ],
    )
    return render(request, PAGE, ctx)


@login_required
@require_POST
def journal_void(request, pk):
    entry = scoped_object(request, JournalEntry.objects.select_related('tenant'), pk)
    require_write(request, entry.tenant)
    reason = request.POST.get('reason', '').strip()
    if entry.is_void:
        messages.error(request, 'El asiento ya está anulado.')
    elif entry.created_by_system:
        messages.error(request, 'Los asientos automáticos no se anulan desde aquí.')
    elif not reason:
        messages.error(request, 'Indica el motivo de la anulación.')
    else:
        entry.is_void, entry.void_reason, entry.voided_at = True, reason, timezone.now()
        entry.save(update_fields=['is_void', 'void_reason', 'voided_at'])
        messages.success(request, 'Asiento anulado.')
    return redirect('panel:journal-detail', pk=pk)


# --------------------------------------------------------------------------- reportes

REPORTS = [('resultados', 'Estado de resultados'), ('pendientes', 'Cobros pendientes'), ('nomina', 'Resumen de nómina')]


@login_required
def reports(request):
    ctx = context(request, section='reports', page_title='Reportes')
    tenant = ctx['tenant']
    report = request.GET.get('r', 'resultados')
    if report not in dict(REPORTS):
        report = 'resultados'
    today = timezone.localdate()
    payroll_ok = ctx['can_payroll']
    if report == 'nomina' and not payroll_ok:
        messages.error(request, 'No tienes permiso para ver la nómina de esta empresa.')
        report = 'resultados'
    tabs = [
        {'key': k, 'label': label, 'url': f'?r={k}', 'active': k == report}
        for k, label in REPORTS
        if k != 'nomina' or payroll_ok
    ]
    ctx.update(tabs=tabs, page_sub=tenant.name)

    if report == 'resultados':
        initial = {'start_date': today.replace(month=1, day=1), 'end_date': today}
        form = (
            DateRangeForm(request.GET or None, initial=initial)
            if 'start_date' in request.GET
            else DateRangeForm(initial=initial)
        )
        values = form.cleaned_data if form.is_bound and form.is_valid() else initial
        data = ReportService.get_income_statement(tenant, values['start_date'], values['end_date'])
        margin = data['net_profit']
        ctx.update(
            report_form=form,
            report_key='resultados',
            notice='Se calcula con los asientos contables no anulados del periodo.',
            kpis=[
                kpi('Ingresos', fmt(data['total_income'])),
                kpi('Gastos', fmt(data['total_expenses']), variant='navy'),
                kpi(
                    'Resultado neto',
                    fmt(margin),
                    'ganancia' if margin >= 0 else 'pérdida',
                    variant='' if margin >= 0 else 'alt',
                    negative=margin < 0,
                ),
            ],
            charts=[
                chart(
                    'chart-income',
                    'Ingresos vs. gastos',
                    'bar',
                    ['Periodo'],
                    [
                        {'label': 'Ingresos', 'data': [f(data['total_income'])], 'color': 'green'},
                        {'label': 'Gastos', 'data': [f(data['total_expenses'])], 'color': 'fuchsia'},
                    ],
                )
            ],
        )
    elif report == 'pendientes':
        items = ReportService.get_outstanding_invoices(tenant)
        rows = [
            {
                'cells': [
                    cell(i['fee_note_number'], sub=i['insurer_name'] or None),
                    status_cell(i['status']),
                    cell(fdate(i['due_date']), sort=str(i['due_date'] or '')),
                    money_cell(i['total_amount'], i['invoice_currency']),
                    money_cell(i['balance_due'], i['invoice_currency']),
                ]
            }
            for i in items
            if i['status'] != 'draft'
        ]
        by_cur = {}
        for i in items:
            if i['status'] != 'draft':
                by_cur[i['invoice_currency']] = by_cur.get(i['invoice_currency'], Decimal('0')) + i['balance_due']
        ctx.update(
            report_key='pendientes',
            notice='No incluye notas en borrador ni anuladas.',
            kpis=[
                kpi(f'Pendiente ({cur})', fmt(v), variant='' if n == 0 else 'navy')
                for n, (cur, v) in enumerate(list(by_cur.items())[:3])
            ],
            tables=[
                table(
                    ['Nota', 'Estado', 'Vence', ('Total', {'num': True}), ('Saldo', {'num': True})],
                    rows,
                    table_id='outstanding',
                    empty='No hay cobros pendientes.',
                )
            ],
        )
    else:
        try:
            year = int(request.GET.get('year', today.year))
        except ValueError:
            year = today.year
        runs = ReportService.get_payroll_summary(tenant, year)
        rows = [
            {
                'cells': [
                    cell(MONTHS[r['month'] - 1].capitalize(), sort=f'{r["month"]:02d}'),
                    status_cell(r['status']),
                    money_cell(r['total_gross']),
                    money_cell(r['total_paye']),
                    money_cell(r['total_nssf_employee'] + r['total_nssf_employer']),
                    money_cell(r['total_net']),
                ]
            }
            for r in runs
        ]
        totals = {k: sum((r[k] for r in runs), Decimal('0')) for k in ('total_gross', 'total_paye', 'total_net')}
        ctx.update(
            report_key='nomina',
            year=year,
            page_actions=[
                act('← ' + str(year - 1), f'?r=nomina&year={year - 1}', method='get'),
                act(str(year + 1) + ' →', f'?r=nomina&year={year + 1}', method='get'),
            ],
            page_sub=f'{tenant.name} · {year}',
            kpis=[
                kpi('Bruto del año', fmt(totals['total_gross'])),
                kpi('PAYE del año', fmt(totals['total_paye']), variant='navy'),
                kpi('Neto del año', fmt(totals['total_net']), variant='alt'),
            ],
            charts=(
                [
                    chart(
                        'chart-year',
                        f'Nómina {year}',
                        'bar',
                        [MONTHS[r['month'] - 1][:3].capitalize() for r in runs],
                        [
                            {'label': 'Bruto', 'data': [f(r['total_gross']) for r in runs], 'color': 'navy'},
                            {'label': 'Neto', 'data': [f(r['total_net']) for r in runs], 'color': 'green'},
                        ],
                    )
                ]
                if runs
                else []
            ),
            tables=[
                table(
                    [
                        'Mes',
                        'Estado',
                        ('Bruto', {'num': True}),
                        ('PAYE', {'num': True}),
                        ('NSSF', {'num': True}),
                        ('Neto', {'num': True}),
                    ],
                    rows,
                    table_id='payroll-year',
                    empty='No hay corridas ese año.',
                    searchable=False,
                )
            ],
        )
    return render(request, PAGE, ctx)
