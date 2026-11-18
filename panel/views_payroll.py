"""Nomina: empleados, complementos y corridas mensuales. Solo roles admin, manager y auditor."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from finance.payroll.models import EmployeeAllowance, EmployeePayrollProfile, PayrollRun
from finance.payroll.services import PayrollService

from .common import context, require_payroll, require_write, scoped_object
from .forms_ops import AllowanceForm, EmployeeForm, PayrollPeriodForm
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


def _gate(request, write=False):
    ctx = context(request)
    require_payroll(request, ctx['tenant'])
    if write:
        require_write(request, ctx['tenant'])
    return ctx


def _label(user):
    return user.get_full_name() or user.get_username()


# --------------------------------------------------------------------------- empleados


@login_required
def employee_list(request):
    ctx = _gate(request)
    tenant = ctx['tenant']
    people = EmployeePayrollProfile.objects.filter(tenant=tenant).select_related('user').order_by('employee_number')
    active = [p for p in people if p.is_active]
    rows = [
        {
            'cells': [
                cell(p.employee_number, href=_url('employee-detail', p.pk), sub=_label(p.user)),
                cell(p.bank_name or '—'),
                cell(fdate(p.start_date), sort=str(p.start_date)),
                money_cell(p.gross_salary),
                status_cell('open' if p.is_active else 'cancelled', 'Activo' if p.is_active else 'Inactivo'),
            ]
        }
        for p in people
    ]
    ctx.update(
        section='employees',
        page_title='Empleados',
        page_sub=tenant.name,
        page_actions=(
            [act('+ Nuevo empleado', _url('employee-create'), style='primary', method='get')]
            if ctx['can_write']
            else []
        ),
        kpis=[
            kpi('Empleados activos', len(active)),
            kpi('Salarios brutos / mes', fmt(sum(p.gross_salary for p in active)), variant='navy'),
        ],
        tables=[
            table(
                ['Empleado', 'Banco', 'Ingreso', ('Salario bruto', {'num': True}), 'Estado'],
                rows,
                table_id='employees',
                empty='Aún no hay empleados.',
            )
        ],
    )
    return render(request, PAGE, ctx)


def _employee_form(request, profile, creating):
    form = EmployeeForm(request.POST or None, instance=profile, tenant=profile.tenant)
    if request.method == 'POST' and form.is_valid():
        saved = form.save(commit=False)
        saved.tenant = profile.tenant
        saved.save()
        messages.success(request, 'Empleado creado.' if creating else 'Empleado actualizado.')
        return redirect('panel:employee-detail', pk=saved.pk)
    ctx = context(
        request,
        obj_tenant=profile.tenant,
        section='employees',
        form=form,
        back_url=_url('employees') if creating else _url('employee-detail', profile.pk),
        page_title='Nuevo empleado' if creating else f'Editar {profile.employee_number}',
        page_sub=profile.tenant.name,
        submit_label='Crear empleado' if creating else 'Guardar cambios',
    )
    return render(request, FORM, ctx)


@login_required
def employee_create(request):
    ctx = _gate(request, write=True)
    return _employee_form(request, EmployeePayrollProfile(tenant=ctx['tenant']), creating=True)


@login_required
def employee_edit(request, pk):
    profile = scoped_object(request, EmployeePayrollProfile.objects.select_related('tenant', 'user'), pk)
    require_payroll(request, profile.tenant)
    require_write(request, profile.tenant)
    return _employee_form(request, profile, creating=False)


@login_required
def employee_detail(request, pk):
    profile = scoped_object(request, EmployeePayrollProfile.objects.select_related('tenant', 'user'), pk)
    ctx = context(request, obj_tenant=profile.tenant, section='employees')
    require_payroll(request, profile.tenant)
    allowances = profile.allowances.order_by('id')
    rows = []
    for a in allowances:
        row_actions = []
        if ctx['can_write']:
            row_actions = [
                act('Desactivar' if a.is_active else 'Activar', _url('allowance-toggle', a.pk)),
                act('Eliminar', _url('allowance-delete', a.pk), style='danger', confirm='¿Eliminar este complemento?'),
            ]
        rows.append(
            {
                'cells': [
                    cell(es(a.allowance_type)),
                    money_cell(a.amount),
                    cell('Sí' if a.is_taxable else 'No'),
                    status_cell('open' if a.is_active else 'cancelled', 'Activo' if a.is_active else 'Inactivo'),
                ],
                'actions': row_actions,
            }
        )
    lines = profile.payroll_lines.select_related('payroll_run').order_by('-payroll_run__year', '-payroll_run__month')[
        :12
    ]
    history = [
        {
            'cells': [
                cell(
                    f'{MONTHS[line.payroll_run.month - 1].capitalize()} {line.payroll_run.year}',
                    href=_url('payroll-detail', line.payroll_run_id),
                ),
                money_cell(line.gross_salary),
                money_cell(line.paye),
                money_cell(line.nssf_employee),
                money_cell(line.net_pay),
            ]
        }
        for line in lines
    ]
    inline = (
        [
            {
                'title': 'Agregar complemento',
                'action': _url('allowance-add', profile.pk),
                'form': AllowanceForm(),
                'cols': 3,
                'submit': 'Agregar',
            }
        ]
        if ctx['can_write']
        else []
    )
    ctx.update(
        back_url=_url('employees'),
        back_label='Empleados',
        page_title=profile.employee_number,
        page_sub=f'{_label(profile.user)} · {profile.tenant.name}',
        badges=[{'text': 'Activo' if profile.is_active else 'Inactivo', 'cls': 'ok' if profile.is_active else 'muted'}],
        page_actions=[act('Editar', _url('employee-edit', profile.pk), method='get')] if ctx['can_write'] else [],
        facts=[
            ('Salario bruto mensual', fmt(profile.gross_salary)),
            ('TIN', profile.tin_number),
            ('N.º NSSF', profile.nssf_number),
            ('Banco', profile.bank_name),
            ('N.º de cuenta', profile.bank_account_number),
            ('Ingreso', fdate(profile.start_date)),
            ('Salida', fdate(profile.end_date)),
        ],
        inline_forms=inline,
        tables=[
            table(
                ['Tipo', ('Monto', {'num': True}), 'Gravable', 'Estado'],
                rows,
                title='Complementos',
                table_id='allowances',
                empty='Sin complementos.',
            ),
            table(
                [
                    'Periodo',
                    ('Bruto', {'num': True}),
                    ('PAYE', {'num': True}),
                    ('NSSF', {'num': True}),
                    ('Neto', {'num': True}),
                ],
                history,
                title='Últimas nóminas',
                table_id='emp-history',
                empty='Aún no aparece en ninguna corrida.',
            ),
        ],
    )
    return render(request, PAGE, ctx)


@login_required
@require_POST
def allowance_add(request, pk):
    profile = scoped_object(request, EmployeePayrollProfile.objects.select_related('tenant'), pk)
    require_payroll(request, profile.tenant)
    require_write(request, profile.tenant)
    form = AllowanceForm(request.POST)
    if form.is_valid():
        allowance = form.save(commit=False)
        allowance.employee = profile
        allowance.save()
        messages.success(request, 'Complemento agregado.')
    else:
        messages.error(request, ' '.join(e for errs in form.errors.values() for e in errs))
    return redirect('panel:employee-detail', pk=pk)


def _allowance(request, pk):
    allowance = scoped_object(
        request, EmployeeAllowance.objects.select_related('employee__tenant'), pk, path='employee__tenant'
    )
    require_payroll(request, allowance.employee.tenant)
    require_write(request, allowance.employee.tenant)
    return allowance


@login_required
@require_POST
def allowance_toggle(request, pk):
    allowance = _allowance(request, pk)
    allowance.is_active = not allowance.is_active
    allowance.save(update_fields=['is_active'])
    messages.success(request, 'Complemento actualizado.')
    return redirect('panel:employee-detail', pk=allowance.employee_id)


@login_required
@require_POST
def allowance_delete(request, pk):
    allowance = _allowance(request, pk)
    employee_id = allowance.employee_id
    allowance.delete()
    messages.success(request, 'Complemento eliminado.')
    return redirect('panel:employee-detail', pk=employee_id)


# --------------------------------------------------------------------------- corridas

STATUS_PERIOD = lambda run: f'{MONTHS[run.month - 1].capitalize()} {run.year}'  # noqa: E731


@login_required
def payroll_list(request):
    ctx = _gate(request)
    tenant = ctx['tenant']
    runs = PayrollRun.objects.filter(tenant=tenant).order_by('-year', '-month')
    rows = [
        {
            'cells': [
                cell(STATUS_PERIOD(r), href=_url('payroll-detail', r.pk), sort=f'{r.year}{r.month:02d}'),
                status_cell(r.status),
                money_cell(r.total_gross),
                money_cell(r.total_paye),
                money_cell(r.total_nssf_employee + r.total_nssf_employer),
                money_cell(r.total_net),
            ]
        }
        for r in runs
    ]
    recent = list(runs[:12])[::-1]
    charts = (
        [
            chart(
                'chart-payroll',
                'Bruto vs. neto por mes',
                'bar',
                [STATUS_PERIOD(r) for r in recent],
                [
                    {'label': 'Bruto', 'data': [f(r.total_gross) for r in recent], 'color': 'navy'},
                    {'label': 'Neto', 'data': [f(r.total_net) for r in recent], 'color': 'green'},
                ],
            )
        ]
        if recent
        else []
    )
    ctx.update(
        section='payroll',
        page_title='Corridas de nómina',
        page_sub=tenant.name,
        charts=charts,
        notice=(
            'Calcular una corrida usa los empleados activos y sus complementos. '
            'Puedes recalcularla mientras esté en borrador.'
        ),
        page_actions=(
            [act('+ Calcular nómina', _url('payroll-create'), style='primary', method='get')]
            if ctx['can_write']
            else []
        ),
        tables=[
            table(
                [
                    'Periodo',
                    'Estado',
                    ('Bruto', {'num': True}),
                    ('PAYE', {'num': True}),
                    ('NSSF (5% + 10%)', {'num': True}),
                    ('Neto', {'num': True}),
                ],
                rows,
                table_id='runs',
                empty='Aún no hay corridas.',
            )
        ],
    )
    return render(request, PAGE, ctx)


@login_required
def payroll_create(request):
    ctx = _gate(request, write=True)
    tenant = ctx['tenant']
    form = PayrollPeriodForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        month, year = form.cleaned_data['month'], form.cleaned_data['year']
        if not EmployeePayrollProfile.objects.filter(tenant=tenant, is_active=True).exists():
            form.add_error(None, 'No hay empleados activos para calcular la nómina.')
        else:
            existing = PayrollRun.objects.filter(tenant=tenant, month=month, year=year).first()
            if existing and existing.status != 'draft':
                form.add_error(None, 'Esa nómina ya fue aprobada o pagada y no se puede recalcular.')
            else:
                run = PayrollService.run_monthly_payroll(tenant, month, year, request.user)
                messages.success(request, 'Nómina calculada.')
                return redirect('panel:payroll-detail', pk=run.pk)
    ctx.update(
        section='payroll',
        form=form,
        back_url=_url('payroll'),
        page_title='Calcular nómina',
        page_sub=f'{tenant.name} · si el periodo ya existe en borrador, se recalcula.',
        submit_label='Calcular',
    )
    return render(request, FORM, ctx)


@login_required
def payroll_detail(request, pk):
    run = scoped_object(request, PayrollRun.objects.select_related('tenant', 'approved_by'), pk)
    ctx = context(request, obj_tenant=run.tenant, section='payroll')
    require_payroll(request, run.tenant)
    lines = list(run.lines.select_related('employee__user').order_by('employee__employee_number'))
    rows = [
        {
            'cells': [
                cell(
                    line.employee.employee_number,
                    href=_url('employee-detail', line.employee_id),
                    sub=_label(line.employee.user),
                ),
                money_cell(line.gross_salary),
                money_cell(line.total_allowances),
                money_cell(line.paye),
                money_cell(line.nssf_employee),
                money_cell(line.nssf_employer),
                money_cell(line.net_pay),
            ]
        }
        for line in lines
    ]
    actions = []
    if ctx['can_write']:
        if run.status == 'draft':
            actions = [
                act(
                    'Recalcular',
                    _url('payroll-action', run.pk, 'recalculate'),
                    confirm='¿Recalcular con los datos actuales de los empleados?',
                )
            ]
            if lines:
                actions.append(
                    act(
                        'Aprobar',
                        _url('payroll-action', run.pk, 'approve'),
                        style='primary',
                        confirm='¿Aprobar esta nómina? Ya no se podrá recalcular.',
                    )
                )
        elif run.status == 'approved':
            actions = [
                act(
                    'Marcar como pagada',
                    _url('payroll-action', run.pk, 'pay'),
                    style='primary',
                    confirm='¿Confirmas que la nómina ya fue pagada?',
                )
            ]
    breakdown = [
        ('Neto a empleados', f(run.total_net)),
        ('PAYE', f(run.total_paye)),
        ('NSSF empleado', f(run.total_nssf_employee)),
        ('NSSF empleador', f(run.total_nssf_employer)),
    ]
    charts = (
        [
            chart(
                'chart-cost',
                'Destino del costo de nómina',
                'doughnut',
                [b[0] for b in breakdown],
                [{'data': [b[1] for b in breakdown], 'color': ['green', 'navy', 'fuchsia', 'pink']}],
            )
        ]
        if lines
        else []
    )
    employer_cost = run.total_gross + run.total_nssf_employer
    ctx.update(
        back_url=_url('payroll'),
        back_label='Corridas de nómina',
        page_title=f'Nómina de {STATUS_PERIOD(run)}',
        badges=[{'text': es(run.status), 'cls': status_cell(run.status)['badge']}],
        page_sub=f'{run.tenant.name}'
        + (f' · aprobada por {run.approved_by} el {fdate(run.approved_at)}' if run.approved_by else ''),
        page_actions=actions,
        charts=charts,
        kpis=[
            kpi('Bruto', fmt(run.total_gross), f'{len(lines)} empleados', variant='navy'),
            kpi('PAYE', fmt(run.total_paye)),
            kpi(
                'NSSF total',
                fmt(run.total_nssf_employee + run.total_nssf_employer),
                'empleado + empleador',
                variant='alt',
            ),
            kpi('Neto a pagar', fmt(run.total_net), f'Costo empleador: {fmt(employer_cost)}'),
        ],
        tables=[
            table(
                [
                    'Empleado',
                    ('Bruto', {'num': True}),
                    ('Complementos', {'num': True}),
                    ('PAYE', {'num': True}),
                    ('NSSF empl.', {'num': True}),
                    ('NSSF patrón', {'num': True}),
                    ('Neto', {'num': True}),
                ],
                rows,
                title='Detalle por empleado',
                table_id='run-lines',
                empty='La corrida no tiene líneas.',
            )
        ],
    )
    return render(request, PAGE, ctx)


@login_required
@require_POST
def payroll_action(request, pk, action):
    run = scoped_object(request, PayrollRun.objects.select_related('tenant'), pk)
    require_payroll(request, run.tenant)
    require_write(request, run.tenant)
    if action == 'recalculate' and run.status == 'draft':
        PayrollService.run_monthly_payroll(run.tenant, run.month, run.year, request.user)
        messages.success(request, 'Nómina recalculada.')
    elif action == 'approve' and run.status == 'draft' and run.lines.exists():
        run.status, run.approved_by, run.approved_at = 'approved', request.user, timezone.now()
        run.save(update_fields=['status', 'approved_by', 'approved_at'])
        messages.success(request, 'Nómina aprobada.')
    elif action == 'pay' and run.status == 'approved':
        run.status = 'paid'
        run.save(update_fields=['status'])
        messages.success(request, 'Nómina marcada como pagada.')
    else:
        messages.error(request, 'Esa acción no es válida para el estado actual de la nómina.')
    return redirect('panel:payroll-detail', pk=pk)
