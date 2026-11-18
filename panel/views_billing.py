"""Notas de honorarios, pagos recibidos y creditos de retencion (WHT)."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Sum
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from finance.invoicing.models import FeeNote
from finance.invoicing.services import FeeNoteService
from finance.payments.models import FeeNotePayment, WHTCredit
from finance.payments.services import PaymentService

from .common import context, require_write, safe_next, scoped_object
from .forms_ops import FeeNoteForm, PaymentForm, ReminderForm
from .ui import act, cell, chart, es, fdate, fmt, kpi, money_cell, status_cell, table

PAGE = 'panel/generic_page.html'
FORM = 'panel/generic_form.html'
STATUS_ORDER = ['draft', 'submitted', 'stamped', 'sent', 'partial', 'paid', 'overdue_1', 'overdue_2', 'overdue_3']
PAYABLE = ('submitted', 'stamped', 'sent', 'partial', 'overdue_1', 'overdue_2', 'overdue_3')
STATUS_COLORS = {
    'draft': 'muted',
    'submitted': 'sky',
    'stamped': 'sky',
    'sent': 'navy',
    'partial': 'amber',
    'paid': 'green',
    'overdue_1': 'pink',
    'overdue_2': 'fuchsia',
    'overdue_3': 'fuchsia',
}


def _url(name, *args):
    return reverse(f'panel:{name}', args=args)


# --------------------------------------------------------------------------- notas de honorarios


@login_required
def invoice_list(request):
    ctx = context(request, section='invoices', page_title='Notas de honorarios')
    tenant = ctx['tenant']
    if not tenant:
        return render(request, PAGE, ctx)

    notes = FeeNote.objects.filter(tenant=tenant)
    status = request.GET.get('status', '')
    shown = notes.filter(status=status) if status else notes
    live = notes.filter(is_void=False)

    receivable = live.exclude(status__in=['paid', 'draft']).values('invoice_currency').annotate(t=Sum('balance_due'))
    kpis = [
        kpi(f'Por cobrar ({row["invoice_currency"]})', fmt(row['t']), variant='' if i == 0 else 'navy')
        for i, row in enumerate(receivable[:2])
    ]
    overdue = live.filter(status__startswith='overdue').count()
    kpis.append(
        kpi(
            'Notas vencidas',
            overdue,
            'más de 30 días sin cobrar' if overdue else 'al día',
            variant='alt' if overdue else 'navy',
        )
    )
    kpis.append(kpi('Total de notas', notes.count(), f'{live.filter(status="paid").count()} pagadas'))

    counts = {row['status']: row['n'] for row in live.values('status').annotate(n=Count('id'))} if live.exists() else {}
    present = [s for s in STATUS_ORDER if counts.get(s)]
    charts = (
        [
            chart(
                'chart-status',
                'Notas por estado',
                'doughnut',
                [es(s) for s in present],
                [{'data': [counts[s] for s in present], 'color': [STATUS_COLORS[s] for s in present]}],
            )
        ]
        if present
        else []
    )

    rows = []
    for n in shown.order_by('-created_at'):
        rows.append(
            {
                'cells': [
                    cell(n.fee_note_number, href=_url('invoice-detail', n.pk), sub=n.insurer_name or None),
                    status_cell(n.status),
                    cell(fdate(n.due_date), sort=str(n.due_date or '')),
                    money_cell(n.total_amount, n.invoice_currency),
                    money_cell(n.balance_due, n.invoice_currency, cls='neg' if n.status.startswith('overdue') else ''),
                ]
            }
        )

    actions = []
    if ctx['can_write']:
        actions = [
            act(
                'Actualizar vencidas',
                _url('invoice-refresh'),
                confirm='¿Marcar como vencidas las notas que ya pasaron su fecha?',
            ),
            act('+ Nueva nota', _url('invoice-create'), style='primary', method='get'),
        ]
    ctx.update(
        page_sub=tenant.name,
        kpis=kpis,
        charts=charts,
        page_actions=actions,
        filters=[
            {
                'name': 'status',
                'label': 'Estado',
                'current': status,
                'choices': [(s, es(s)) for s in STATUS_ORDER + ['void']],
            }
        ],
        filters_active=bool(status),
        tables=[
            table(
                ['Nota', 'Estado', 'Vence', ('Total', {'num': True}), ('Saldo', {'num': True})],
                rows,
                table_id='invoices',
                empty='No hay notas de honorarios.',
            )
        ],
    )
    return render(request, PAGE, ctx)


def _note_form(request, note, creating):
    form = FeeNoteForm(request.POST or None, instance=note, tenant=note.tenant)
    if request.method == 'POST' and form.is_valid():
        saved = form.save()
        messages.success(request, 'Nota creada.' if creating else 'Nota actualizada.')
        return redirect('panel:invoice-detail', pk=saved.pk)
    back = _url('invoices') if creating else _url('invoice-detail', note.pk)
    ctx = context(
        request,
        obj_tenant=note.tenant,
        section='invoices',
        form=form,
        back_url=back,
        page_title='Nueva nota de honorarios' if creating else f'Editar {note.fee_note_number}',
        page_sub=f'{note.tenant.name} · queda en borrador hasta enviarla a EFRIS.',
        wide_fields=['insurer_name'],
        submit_label='Crear nota' if creating else 'Guardar cambios',
    )
    return render(request, FORM, ctx)


@login_required
def invoice_create(request):
    ctx = context(request)
    require_write(request, ctx['tenant'])
    return _note_form(request, FeeNote(tenant=ctx['tenant'], created_by=request.user, status='draft'), creating=True)


@login_required
def invoice_edit(request, pk):
    note = scoped_object(request, FeeNote.objects.select_related('tenant'), pk)
    require_write(request, note.tenant)
    if note.status != 'draft' or note.is_void:
        messages.error(request, 'Solo se pueden editar notas en borrador.')
        return redirect('panel:invoice-detail', pk=pk)
    return _note_form(request, note, creating=False)


def _note_actions(note, can_write):
    if not can_write or note.is_void:
        return []
    out = []
    if note.status == 'draft':
        out += [
            act('Editar', _url('invoice-edit', note.pk), method='get'),
            act(
                'Enviar a EFRIS',
                _url('invoice-action', note.pk, 'efris'),
                style='primary',
                confirm='¿Enviar esta nota a EFRIS? Después ya no se podrá editar.',
            ),
        ]
    elif note.status in ('submitted', 'stamped'):
        out.append(
            act(
                'Enviar a la aseguradora',
                _url('invoice-action', note.pk, 'send'),
                style='primary',
                confirm=f'¿Enviar la nota a {note.insurer_email or "la aseguradora"}?',
            )
        )
    if note.status in PAYABLE:
        out += [
            act('Registrar pago', _url('payment-create', note.pk), style='primary', method='get'),
            act('Registrar recordatorio', _url('reminder-create', note.pk), method='get'),
        ]
    if note.status != 'paid' and not note.amount_paid:
        out.append(
            act(
                'Anular',
                _url('invoice-action', note.pk, 'void'),
                style='danger',
                prompt='Motivo de la anulación (obligatorio)',
            )
        )
    return out


@login_required
def invoice_detail(request, pk):
    note = scoped_object(request, FeeNote.objects.select_related('tenant', 'created_by', 'voided_by'), pk)
    ctx = context(request, obj_tenant=note.tenant, section='invoices')
    cur = note.invoice_currency

    payments = [
        {
            'cells': [
                cell(fdate(p.payment_date), sort=str(p.payment_date)),
                cell(es(p.payment_method)),
                cell(p.bank_reference or '—'),
                money_cell(p.amount_received_foreign, cur),
                money_cell(p.wht_amount if p.wht_deducted else None, cur),
                money_cell(
                    p.fx_gain_loss, '', cls='pos' if p.fx_gain_loss > 0 else 'neg' if p.fx_gain_loss < 0 else ''
                ),
            ]
        }
        for p in note.payments.order_by('-payment_date', '-id')
    ]
    reminders = [
        {
            'cells': [
                cell(r.sent_at.strftime('%d/%m/%Y %H:%M'), sort=r.sent_at.isoformat()),
                cell(es(r.reminder_type)),
                cell(r.sent_to),
                status_cell('paid' if r.success else 'bounced', 'Registrado' if r.success else 'Falló'),
            ]
        }
        for r in note.reminders.order_by('-sent_at')
    ]

    facts = [
        ('Aseguradora', note.insurer_name),
        ('Correo', note.insurer_email),
        ('Moneda', cur),
        ('Monto sin IVA', f'{fmt(note.invoice_amount)} {cur}'),
        ('IVA', f'{fmt(note.vat_amount)} {cur}'),
        ('Tasa de cambio al emitir', f'{note.exchange_rate_at_issue:,.4f}'),
        ('Monto en moneda base (EFRIS)', fmt(note.ugx_amount_efris)),
        ('Vence', fdate(note.due_date)),
        ('N.º fiscal EFRIS', note.efris_fiscal_number),
        ('Enviada a la aseguradora', note.sent_at.strftime('%d/%m/%Y %H:%M') if note.sent_at else '—'),
        ('Creada por', note.created_by.get_username() if note.created_by else '—'),
        ('ID del siniestro', str(note.claim_id)),
    ]
    if note.is_void:
        facts.append(('Anulada', f'{note.void_reason} ({fdate(note.voided_at)}, {note.voided_by or "—"})'))

    fx_total = sum((p.fx_gain_loss for p in note.payments.all()), 0)
    ctx.update(
        back_url=_url('invoices'),
        back_label='Notas de honorarios',
        page_title=note.fee_note_number,
        badges=[{'text': es(note.status), 'cls': status_cell(note.status)['badge']}],
        page_sub=f'{note.insurer_name or "Sin aseguradora"} · {note.tenant.name}',
        page_actions=_note_actions(note, ctx['can_write']),
        kpis=[
            kpi('Total', fmt(note.total_amount), cur, variant='navy'),
            kpi('Pagado', fmt(note.amount_paid), cur),
            kpi(
                'Saldo pendiente',
                fmt(note.balance_due),
                cur,
                variant='alt' if note.balance_due else '',
                negative=note.balance_due > 0 and note.status.startswith('overdue'),
            ),
            kpi('Ganancia / pérdida cambiaria', fmt(fx_total), 'acumulada', variant='navy'),
        ],
        facts=facts,
        facts_title='Datos de la nota',
        tables=[
            table(
                [
                    'Fecha',
                    'Método',
                    'Referencia',
                    ('Monto', {'num': True}),
                    ('Retención', {'num': True}),
                    ('Dif. cambiaria', {'num': True}),
                ],
                payments,
                title='Pagos recibidos',
                table_id='note-payments',
                empty='Aún no se han registrado pagos.',
            ),
            table(
                ['Fecha', 'Tipo', 'Enviado a', 'Resultado'],
                reminders,
                title='Recordatorios',
                table_id='note-reminders',
                empty='Sin recordatorios.',
            ),
        ],
    )
    return render(request, PAGE, ctx)


@login_required
@require_POST
def invoice_action(request, pk, action):
    note = scoped_object(request, FeeNote.objects.select_related('tenant'), pk)
    require_write(request, note.tenant)
    if note.is_void:
        messages.error(request, 'La nota está anulada.')
    elif action == 'efris':
        if note.status != 'draft':
            messages.error(request, 'Solo se envían a EFRIS las notas en borrador.')
        else:
            FeeNoteService.submit_to_efris(note)
            messages.success(request, 'Nota enviada a EFRIS.')
    elif action == 'send':
        if note.status not in ('submitted', 'stamped'):
            messages.error(request, 'La nota primero debe enviarse a EFRIS.')
        elif not note.insurer_email:
            messages.error(request, 'La nota no tiene correo de la aseguradora. Edítala antes de enviarla.')
        else:
            FeeNoteService.send_to_insurer(note, request.user)
            messages.success(request, f'Nota marcada como enviada a {note.insurer_email}.')
    elif action == 'void':
        reason = request.POST.get('reason', '').strip()
        if note.status == 'paid' or note.amount_paid:
            messages.error(request, 'No se puede anular una nota con pagos registrados.')
        elif not reason:
            messages.error(request, 'Indica el motivo de la anulación.')
        else:
            FeeNoteService.void_fee_note(note, reason, request.user)
            messages.success(request, 'Nota anulada.')
    else:
        messages.error(request, 'Acción desconocida.')
    return redirect('panel:invoice-detail', pk=pk)


@login_required
@require_POST
def invoice_refresh(request):
    ctx = context(request)
    require_write(request, ctx['tenant'])
    FeeNoteService.update_overdue_statuses(ctx['tenant'])
    messages.success(request, 'Estados de vencimiento actualizados.')
    return redirect('panel:invoices')


@login_required
def payment_create(request, pk):
    note = scoped_object(request, FeeNote.objects.select_related('tenant'), pk)
    require_write(request, note.tenant)
    if note.is_void or note.status not in PAYABLE:
        messages.error(request, 'Solo se registran pagos en notas ya enviadas y con saldo pendiente.')
        return redirect('panel:invoice-detail', pk=pk)
    form = PaymentForm(request.POST or None, fee_note=note)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            PaymentService.record_payment(note, form.payload(), request.user)
        messages.success(request, 'Pago registrado.')
        return redirect('panel:invoice-detail', pk=pk)
    cur = note.invoice_currency
    ctx = context(
        request,
        obj_tenant=note.tenant,
        section='invoices',
        form=form,
        back_url=_url('invoice-detail', pk),
        page_title=f'Registrar pago · {note.fee_note_number}',
        page_sub=note.tenant.name,
        facts=[
            ('Total', f'{fmt(note.total_amount)} {cur}'),
            ('Pagado', f'{fmt(note.amount_paid)} {cur}'),
            ('Saldo pendiente', f'{fmt(note.balance_due)} {cur}'),
        ],
        wide_fields=['bank_reference'],
        submit_label='Registrar pago',
    )
    return render(request, FORM, ctx)


@login_required
def reminder_create(request, pk):
    note = scoped_object(request, FeeNote.objects.select_related('tenant'), pk)
    require_write(request, note.tenant)
    if note.is_void or note.status not in PAYABLE:
        messages.error(request, 'Solo se registran recordatorios en notas enviadas y pendientes de cobro.')
        return redirect('panel:invoice-detail', pk=pk)
    form = ReminderForm(request.POST or None, fee_note=note)
    if request.method == 'POST' and form.is_valid():
        reminder = form.save(commit=False)
        reminder.fee_note, reminder.success = note, True
        reminder.save()
        messages.success(request, 'Recordatorio registrado.')
        return redirect('panel:invoice-detail', pk=pk)
    ctx = context(
        request,
        obj_tenant=note.tenant,
        section='invoices',
        form=form,
        back_url=_url('invoice-detail', pk),
        page_title=f'Registrar recordatorio · {note.fee_note_number}',
        page_sub='Esto deja constancia del recordatorio; no envía ningún correo por sí solo.',
        submit_label='Registrar',
    )
    return render(request, FORM, ctx)


# --------------------------------------------------------------------------- pagos y retenciones


@login_required
def payment_list(request):
    ctx = context(request, section='payments', page_title='Pagos recibidos')
    tenant = ctx['tenant']
    if not tenant:
        return render(request, PAGE, ctx)
    payments = FeeNotePayment.objects.filter(tenant=tenant).select_related('fee_note').order_by('-payment_date', '-id')
    totals = payments.aggregate(base=Sum('base_currency_received'), fx=Sum('fx_gain_loss'), wht=Sum('wht_amount'))
    rows = [
        {
            'cells': [
                cell(fdate(p.payment_date), sort=str(p.payment_date)),
                cell(
                    p.fee_note.fee_note_number,
                    href=_url('invoice-detail', p.fee_note_id),
                    sub=p.fee_note.insurer_name or None,
                ),
                cell(es(p.payment_method)),
                cell(p.bank_reference or '—'),
                money_cell(p.amount_received_foreign, p.payment_currency),
                money_cell(p.base_currency_received),
                money_cell(p.fx_gain_loss, cls='pos' if p.fx_gain_loss > 0 else 'neg' if p.fx_gain_loss < 0 else ''),
            ]
        }
        for p in payments
    ]
    ctx.update(
        page_sub=tenant.name,
        kpis=[
            kpi('Cobrado (moneda base)', fmt(totals['base'] or 0), f'{len(rows)} pagos'),
            kpi('Ganancia / pérdida cambiaria', fmt(totals['fx'] or 0), variant='navy'),
            kpi('Retenciones aplicadas', fmt(totals['wht'] or 0), variant='alt'),
        ],
        tables=[
            table(
                [
                    'Fecha',
                    'Nota',
                    'Método',
                    'Referencia',
                    ('Monto', {'num': True}),
                    ('En moneda base', {'num': True}),
                    ('Dif. cambiaria', {'num': True}),
                ],
                rows,
                table_id='payments',
                empty='Aún no se han registrado pagos.',
            )
        ],
    )
    return render(request, PAGE, ctx)


@login_required
def wht_list(request):
    ctx = context(request, section='wht', page_title='Créditos de retención (WHT)')
    tenant = ctx['tenant']
    if not tenant:
        return render(request, PAGE, ctx)
    credits = (
        WHTCredit.objects.filter(tenant=tenant)
        .select_related('payment__fee_note')
        .order_by('-period_year', '-period_month', '-id')
    )
    available = sum((c.amount for c in credits if not c.is_utilised), 0)
    used = sum((c.amount for c in credits if c.is_utilised), 0)
    rows = []
    for c in credits:
        row_actions = []
        if ctx['can_write']:
            label = 'Marcar disponible' if c.is_utilised else 'Marcar utilizado'
            row_actions.append(act(label, _url('wht-toggle', c.pk), style='' if c.is_utilised else 'primary'))
        rows.append(
            {
                'cells': [
                    cell(c.cert_number),
                    cell(f'{c.period_month:02d}/{c.period_year}', sort=f'{c.period_year}{c.period_month:02d}'),
                    cell(c.payment.fee_note.fee_note_number, href=_url('invoice-detail', c.payment.fee_note_id)),
                    money_cell(c.amount),
                    status_cell('locked' if c.is_utilised else 'open', 'Utilizado' if c.is_utilised else 'Disponible'),
                ],
                'actions': row_actions,
            }
        )
    ctx.update(
        page_sub=f'{tenant.name} · se generan al registrar un pago con retención.',
        kpis=[kpi('Disponible para compensar', fmt(available)), kpi('Ya utilizado', fmt(used), variant='navy')],
        tables=[
            table(
                ['Certificado', 'Periodo', 'Nota', ('Monto', {'num': True}), 'Estado'],
                rows,
                table_id='wht',
                empty='No hay créditos de retención.',
            )
        ],
    )
    return render(request, PAGE, ctx)


@login_required
@require_POST
def wht_toggle(request, pk):
    credit = scoped_object(request, WHTCredit.objects.select_related('tenant'), pk)
    require_write(request, credit.tenant)
    credit.is_utilised = not credit.is_utilised
    credit.utilised_at = timezone.now() if credit.is_utilised else None
    credit.save(update_fields=['is_utilised', 'utilised_at'])
    messages.success(
        request, 'Crédito marcado como utilizado.' if credit.is_utilised else 'Crédito marcado como disponible.'
    )
    return redirect(safe_next(request, 'panel:wht'))
