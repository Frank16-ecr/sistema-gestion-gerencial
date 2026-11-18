"""Tesoreria: cuentas bancarias, conciliaciones, caja chica y cheques."""

from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import F, Sum
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from finance.banking.models import BankAccount, BankReconciliation, Cheque, PettyCashTransaction

from .common import context, require_write, scoped_object
from .forms_ops import BankAccountForm, ChequeForm, PettyCashForm, ReconciliationForm
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


def _url(name, *args):
    return reverse(f'panel:{name}', args=args)


def _form_page(request, form, *, tenant, section, back, title, sub='', submit='Guardar', **extra):
    ctx = context(
        request,
        obj_tenant=tenant,
        section=section,
        form=form,
        back_url=back,
        page_title=title,
        page_sub=sub or tenant.name,
        submit_label=submit,
        **extra,
    )
    return render(request, FORM, ctx)


# --------------------------------------------------------------------------- cuentas bancarias


@login_required
def bank_account_list(request):
    ctx = context(request, section='bank_accounts', page_title='Cuentas bancarias')
    tenant = ctx['tenant']
    accounts = BankAccount.objects.filter(tenant=tenant).order_by('-is_active', 'account_name')
    totals = {}
    for a in accounts:
        if a.is_active:
            totals[a.currency] = totals.get(a.currency, Decimal('0')) + a.current_balance
    rows = [
        {
            'cells': [
                cell(
                    a.account_name, href=_url('bank-account-edit', a.pk) if ctx['can_write'] else None, sub=a.bank_name
                ),
                cell(a.account_number),
                cell(es(a.account_type)),
                money_cell(a.current_balance, a.currency, cls='neg' if a.current_balance < 0 else ''),
                status_cell('open' if a.is_active else 'cancelled', 'Activa' if a.is_active else 'Inactiva'),
            ]
        }
        for a in accounts
    ]
    kpis = [
        kpi(f'Saldo total ({cur})', fmt(v), variant='' if i == 0 else 'navy')
        for i, (cur, v) in enumerate(list(totals.items())[:3])
    ]
    ctx.update(
        page_sub=tenant.name,
        kpis=kpis,
        page_actions=(
            [act('+ Nueva cuenta', _url('bank-account-create'), style='primary', method='get')]
            if ctx['can_write']
            else []
        ),
        tables=[
            table(
                ['Cuenta', 'N.º', 'Tipo', ('Saldo actual', {'num': True}), 'Estado'],
                rows,
                table_id='accounts',
                empty='Aún no hay cuentas bancarias.',
                sub='El saldo actual cambia con la caja chica y los cheques cobrados.',
            )
        ],
    )
    return render(request, PAGE, ctx)


@login_required
def bank_account_create(request):
    ctx = context(request)
    require_write(request, ctx['tenant'])
    tenant = ctx['tenant']
    form = BankAccountForm(request.POST or None, tenant=tenant)
    if request.method == 'POST' and form.is_valid():
        account = form.save(commit=False)
        account.tenant = tenant
        account.current_balance = account.opening_balance
        account.save()
        messages.success(request, 'Cuenta creada.')
        return redirect('panel:bank-accounts')
    return _form_page(
        request,
        form,
        tenant=tenant,
        section='bank_accounts',
        back=_url('bank-accounts'),
        title='Nueva cuenta bancaria',
        submit='Crear cuenta',
    )


@login_required
def bank_account_edit(request, pk):
    account = scoped_object(request, BankAccount.objects.select_related('tenant'), pk)
    require_write(request, account.tenant)
    form = BankAccountForm(request.POST or None, instance=account, tenant=account.tenant)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Cuenta actualizada.')
        return redirect('panel:bank-accounts')
    return _form_page(
        request,
        form,
        tenant=account.tenant,
        section='bank_accounts',
        back=_url('bank-accounts'),
        title=f'Editar {account.account_name}',
        sub='El saldo inicial y la moneda no se pueden cambiar.',
        submit='Guardar cambios',
    )


# --------------------------------------------------------------------------- conciliaciones


@login_required
def reconciliation_list(request):
    ctx = context(request, section='reconciliations', page_title='Conciliaciones bancarias')
    tenant = ctx['tenant']
    recs = (
        BankReconciliation.objects.filter(tenant=tenant)
        .select_related('bank_account')
        .order_by('-period_year', '-period_month', '-id')
    )
    rows = []
    for r in recs:
        diff = r.closing_balance_per_bank - r.closing_balance_per_system
        rows.append(
            {
                'cells': [
                    cell(
                        f'{MONTHS[r.period_month - 1].capitalize()} {r.period_year}',
                        href=_url('reconciliation-detail', r.pk),
                        sort=f'{r.period_year}{r.period_month:02d}',
                        sub=r.bank_account.account_name,
                    ),
                    money_cell(r.closing_balance_per_bank, r.bank_account.currency),
                    money_cell(r.closing_balance_per_system, r.bank_account.currency),
                    money_cell(diff, '', cls='neg' if diff else 'pos'),
                    status_cell(r.status),
                ]
            }
        )
    open_count = sum(1 for r in recs if r.status == 'open')
    ctx.update(
        page_sub=tenant.name,
        kpis=[
            kpi('Conciliaciones abiertas', open_count, variant='alt' if open_count else ''),
            kpi('Cerradas', len(recs) - open_count, variant='navy'),
        ],
        page_actions=(
            [act('+ Nueva conciliación', _url('reconciliation-create'), style='primary', method='get')]
            if ctx['can_write']
            else []
        ),
        tables=[
            table(
                [
                    'Periodo',
                    ('Según banco', {'num': True}),
                    ('Según sistema', {'num': True}),
                    ('Diferencia', {'num': True}),
                    'Estado',
                ],
                rows,
                table_id='recs',
                empty='Aún no hay conciliaciones.',
            )
        ],
    )
    return render(request, PAGE, ctx)


@login_required
def reconciliation_create(request):
    ctx = context(request)
    require_write(request, ctx['tenant'])
    tenant = ctx['tenant']
    form = ReconciliationForm(request.POST or None, tenant=tenant)
    if request.method == 'POST' and form.is_valid():
        rec = form.save(commit=False)
        rec.tenant = tenant
        rec.save()
        messages.success(request, 'Conciliación creada.')
        return redirect('panel:reconciliation-detail', pk=rec.pk)
    return _form_page(
        request,
        form,
        tenant=tenant,
        section='reconciliations',
        back=_url('reconciliations'),
        title='Nueva conciliación',
        submit='Crear conciliación',
    )


@login_required
def reconciliation_detail(request, pk):
    rec = scoped_object(request, BankReconciliation.objects.select_related('tenant', 'bank_account', 'locked_by'), pk)
    ctx = context(request, obj_tenant=rec.tenant, section='reconciliations')
    cur = rec.bank_account.currency
    diff = rec.closing_balance_per_bank - rec.closing_balance_per_system
    actions = []
    if ctx['can_write'] and rec.status == 'open':
        actions = [
            act(
                'Cerrar conciliación',
                _url('reconciliation-lock', rec.pk),
                style='primary',
                confirm='¿Cerrar la conciliación? Ya no se podrá cambiar.'
                + (f' Atención: hay una diferencia de {fmt(diff)}.' if diff else ''),
            )
        ]
    ctx.update(
        back_url=_url('reconciliations'),
        back_label='Conciliaciones',
        page_title=f'{MONTHS[rec.period_month - 1].capitalize()} {rec.period_year} · {rec.bank_account.account_name}',
        badges=[{'text': es(rec.status), 'cls': status_cell(rec.status)['badge']}],
        page_sub=rec.tenant.name,
        page_actions=actions,
        kpis=[
            kpi('Saldo inicial', fmt(rec.opening_balance), cur, variant='navy'),
            kpi('Final según banco', fmt(rec.closing_balance_per_bank), cur),
            kpi('Final según sistema', fmt(rec.closing_balance_per_system), cur),
            kpi(
                'Diferencia',
                fmt(diff),
                'conciliada' if not diff else 'revisar partidas',
                variant='' if not diff else 'alt',
                negative=bool(diff),
            ),
        ],
        facts=[
            ('Notas', rec.notes),
            ('Cerrada', f'{rec.locked_at:%d/%m/%Y %H:%M} por {rec.locked_by}' if rec.locked_at else '—'),
        ],
    )
    return render(request, PAGE, ctx)


@login_required
@require_POST
def reconciliation_lock(request, pk):
    rec = scoped_object(request, BankReconciliation.objects.select_related('tenant'), pk)
    require_write(request, rec.tenant)
    if rec.status != 'open':
        messages.error(request, 'La conciliación ya está cerrada.')
    else:
        rec.status, rec.locked_at, rec.locked_by = 'locked', timezone.now(), request.user
        rec.save(update_fields=['status', 'locked_at', 'locked_by'])
        messages.success(request, 'Conciliación cerrada.')
    return redirect('panel:reconciliation-detail', pk=pk)


# --------------------------------------------------------------------------- caja chica


@login_required
def petty_cash_list(request):
    ctx = context(request, section='petty_cash', page_title='Caja chica')
    tenant = ctx['tenant']
    boxes = BankAccount.objects.filter(tenant=tenant, account_type='petty_cash', is_active=True)
    movements = (
        PettyCashTransaction.objects.filter(tenant=tenant)
        .select_related('bank_account')
        .order_by('-transaction_date', '-id')
    )
    rows = []
    for m in movements:
        sign = -1 if m.transaction_type == 'withdrawal' else 1
        rows.append(
            {
                'cells': [
                    cell(fdate(m.transaction_date), sort=str(m.transaction_date)),
                    cell(m.description, sub=m.bank_account.account_name),
                    status_cell('cancelled' if sign < 0 else 'paid', es(m.transaction_type)),
                    cell(m.reference or '—'),
                    money_cell(sign * m.amount, m.bank_account.currency, cls='neg' if sign < 0 else 'pos'),
                ]
            }
        )
    withdrawals = movements.filter(transaction_type='withdrawal')
    by_month = {}
    for m in withdrawals:
        key = f'{m.transaction_date.year}-{m.transaction_date.month:02d}'
        by_month[key] = by_month.get(key, Decimal('0')) + m.amount
    keys = sorted(by_month)[-6:]
    charts = (
        [
            chart(
                'chart-petty',
                'Retiros por mes',
                'bar',
                keys,
                [{'label': 'Retiros', 'data': [f(by_month[k]) for k in keys], 'color': 'fuchsia'}],
            )
        ]
        if keys
        else []
    )
    ctx.update(
        page_sub=tenant.name,
        charts=charts,
        kpis=[
            kpi(f'Saldo · {b.account_name}', fmt(b.current_balance), b.currency, variant='' if i == 0 else 'navy')
            for i, b in enumerate(boxes[:3])
        ],
        notice=None if boxes else 'Primero crea una cuenta de tipo «Caja chica» en Cuentas bancarias.',
        page_actions=(
            [act('+ Registrar movimiento', _url('petty-cash-create'), style='primary', method='get')]
            if ctx['can_write'] and boxes
            else []
        ),
        tables=[
            table(
                ['Fecha', 'Descripción', 'Tipo', 'Referencia', ('Monto', {'num': True})],
                rows,
                table_id='petty',
                empty='Aún no hay movimientos de caja chica.',
            )
        ],
    )
    return render(request, PAGE, ctx)


@login_required
def petty_cash_create(request):
    ctx = context(request)
    require_write(request, ctx['tenant'])
    tenant = ctx['tenant']
    form = PettyCashForm(request.POST or None, tenant=tenant)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            account = BankAccount.objects.select_for_update().get(pk=form.cleaned_data['bank_account'].pk)
            amount, kind = form.cleaned_data['amount'], form.cleaned_data['transaction_type']
            if kind == 'withdrawal' and amount > account.current_balance:
                form.add_error('amount', f'Saldo insuficiente en la caja ({account.current_balance:,.2f}).')
            else:
                movement = form.save(commit=False)
                movement.tenant, movement.recorded_by = tenant, request.user
                movement.save()
                BankAccount.objects.filter(pk=account.pk).update(
                    current_balance=F('current_balance') + (-amount if kind == 'withdrawal' else amount)
                )
                messages.success(request, 'Movimiento registrado.')
                return redirect('panel:petty-cash')
    return _form_page(
        request,
        form,
        tenant=tenant,
        section='petty_cash',
        back=_url('petty-cash'),
        title='Movimiento de caja chica',
        wide_fields=['description'],
        submit='Registrar',
    )


# --------------------------------------------------------------------------- cheques


@login_required
def cheque_list(request):
    ctx = context(request, section='cheques', page_title='Cheques')
    tenant = ctx['tenant']
    status = request.GET.get('status', '')
    all_cheques = Cheque.objects.filter(tenant=tenant).select_related('bank_account')
    shown = all_cheques.filter(status=status) if status else all_cheques
    rows = []
    for c in shown.order_by('-issue_date', '-id'):
        row_actions = []
        if ctx['can_write'] and c.status == 'pending':
            row_actions = [
                act(
                    'Cobrado',
                    _url('cheque-action', c.pk, 'clear'),
                    style='primary',
                    confirm='¿Marcar el cheque como cobrado? Se ajustará el saldo de la cuenta.',
                ),
                act('Rebotó', _url('cheque-action', c.pk, 'bounce'), confirm='¿Marcar el cheque como rebotado?'),
                act(
                    'Cancelar', _url('cheque-action', c.pk, 'cancel'), style='danger', confirm='¿Cancelar este cheque?'
                ),
            ]
        rows.append(
            {
                'cells': [
                    cell(c.cheque_number, sub=c.bank_account.account_name),
                    cell(es(c.cheque_type)),
                    cell(c.payee_payer),
                    cell(fdate(c.issue_date), sort=str(c.issue_date)),
                    money_cell(c.amount, c.bank_account.currency),
                    status_cell(c.status),
                ],
                'actions': row_actions,
            }
        )
    pending = all_cheques.filter(status='pending')
    pend_in = pending.filter(cheque_type='receipt').aggregate(t=Sum('amount'))['t'] or 0
    pend_out = pending.filter(cheque_type='issued').aggregate(t=Sum('amount'))['t'] or 0
    ctx.update(
        page_sub=tenant.name,
        kpis=[
            kpi('Por cobrar (recibidos)', fmt(pend_in), 'cheques pendientes'),
            kpi('Por pagar (emitidos)', fmt(pend_out), 'cheques pendientes', variant='alt'),
            kpi('Rebotados', all_cheques.filter(status='bounced').count(), variant='navy'),
        ],
        filters=[
            {
                'name': 'status',
                'label': 'Estado',
                'current': status,
                'choices': [(s, es(s)) for s in ('pending', 'cleared', 'bounced', 'cancelled')],
            }
        ],
        filters_active=bool(status),
        page_actions=(
            [act('+ Nuevo cheque', _url('cheque-create'), style='primary', method='get')] if ctx['can_write'] else []
        ),
        tables=[
            table(
                ['Cheque', 'Tipo', 'Beneficiario / ordenante', 'Fecha', ('Monto', {'num': True}), 'Estado'],
                rows,
                table_id='cheques',
                empty='No hay cheques.',
            )
        ],
    )
    return render(request, PAGE, ctx)


@login_required
def cheque_create(request):
    ctx = context(request)
    require_write(request, ctx['tenant'])
    tenant = ctx['tenant']
    form = ChequeForm(request.POST or None, tenant=tenant)
    if request.method == 'POST' and form.is_valid():
        cheque = form.save(commit=False)
        cheque.tenant, cheque.status = tenant, 'pending'
        cheque.save()
        messages.success(request, 'Cheque registrado.')
        return redirect('panel:cheques')
    return _form_page(
        request,
        form,
        tenant=tenant,
        section='cheques',
        back=_url('cheques'),
        title='Nuevo cheque',
        sub=f'{tenant.name} · las cuentas de caja chica no usan cheques.',
        wide_fields=['payee_payer'],
        submit='Registrar cheque',
    )


@login_required
@require_POST
def cheque_action(request, pk, action):
    cheque = scoped_object(request, Cheque.objects.select_related('tenant', 'bank_account'), pk)
    require_write(request, cheque.tenant)
    if cheque.status != 'pending' or action not in ('clear', 'bounce', 'cancel'):
        messages.error(request, 'Solo se pueden cambiar cheques pendientes.')
        return redirect('panel:cheques')
    with transaction.atomic():
        if action == 'clear':
            delta = cheque.amount if cheque.cheque_type == 'receipt' else -cheque.amount
            BankAccount.objects.filter(pk=cheque.bank_account_id).update(current_balance=F('current_balance') + delta)
            cheque.status, cheque.cleared_date = 'cleared', timezone.localdate()
            cheque.save(update_fields=['status', 'cleared_date'])
            messages.success(request, 'Cheque cobrado y saldo de la cuenta actualizado.')
        else:
            cheque.status = 'bounced' if action == 'bounce' else 'cancelled'
            cheque.save(update_fields=['status'])
            messages.success(request, 'Cheque marcado como rebotado.' if action == 'bounce' else 'Cheque cancelado.')
    return redirect('panel:cheques')
