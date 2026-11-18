"""Formularios de facturacion, nomina, tesoreria y contabilidad."""

import uuid
from decimal import Decimal

from django import forms
from django.contrib.auth import get_user_model
from django.forms import inlineformset_factory
from django.utils import timezone

from finance.accounts.models import Account, JournalEntry, JournalLine
from finance.banking.models import BankAccount, BankReconciliation, Cheque, PettyCashTransaction
from finance.invoicing.models import FeeNote, FeeNoteReminder
from finance.payroll.models import EmployeeAllowance, EmployeePayrollProfile

from .forms import CURRENCIES, DATE
from .ui import es

User = get_user_model()
ZERO = Decimal('0')


def spanish(choices):
    return [(value, es(value)) if value else (value, label) for value, label in choices]


def positive(value, message='Debe ser mayor que cero.'):
    if value is None or value <= 0:
        raise forms.ValidationError(message)
    return value


class TenantModelForm(forms.ModelForm):
    """ModelForm con la empresa fija; ayuda con moneda en lista y opciones traducidas."""

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)

    def use_currency(self, name):
        current = getattr(self.instance, name, None) if self.instance.pk else None
        choices = list(CURRENCIES)
        if current and current not in dict(choices):
            choices.append((current, current))
        self.fields[name] = forms.ChoiceField(choices=choices, label='Moneda')
        if not self.instance.pk:
            self.initial[name] = 'USD'

    def translate(self, name):
        self.fields[name].choices = spanish(self.fields[name].choices)


# --------------------------------------------------------------------------- facturacion


class FeeNoteForm(TenantModelForm):
    claim_id = forms.UUIDField(
        required=False,
        label='ID del siniestro (opcional)',
        help_text='Si lo dejas vacío se genera uno automáticamente.',
    )
    insurer_id = forms.UUIDField(required=False, label='ID de la aseguradora (opcional)')

    class Meta:
        model = FeeNote
        fields = (
            'fee_note_number',
            'insurer_name',
            'insurer_email',
            'claim_id',
            'insurer_id',
            'invoice_currency',
            'invoice_amount',
            'vat_amount',
            'exchange_rate_at_issue',
            'due_date',
        )
        labels = {
            'fee_note_number': 'Número de nota',
            'insurer_name': 'Aseguradora',
            'insurer_email': 'Correo de la aseguradora',
            'invoice_amount': 'Monto sin IVA',
            'vat_amount': 'IVA',
            'due_date': 'Fecha de vencimiento',
            'exchange_rate_at_issue': 'Tasa de cambio a la moneda base',
        }
        widgets = {'due_date': DATE}
        help_texts = {'exchange_rate_at_issue': 'Usa 1 si la nota está en la moneda base.'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.use_currency('invoice_currency')
        self.fields['invoice_currency'].label = 'Moneda'
        if not self.instance.pk:
            count = FeeNote.objects.filter(tenant=self.tenant).count() + 1
            self.initial.setdefault('fee_note_number', f'FN-{timezone.localdate():%Y%m%d}-{count:03d}')
            self.initial.setdefault('exchange_rate_at_issue', Decimal('1'))
            self.initial.setdefault('vat_amount', ZERO)

    def clean_invoice_amount(self):
        return positive(self.cleaned_data['invoice_amount'])

    def clean_vat_amount(self):
        value = self.cleaned_data['vat_amount']
        if value is not None and value < 0:
            raise forms.ValidationError('No puede ser negativo.')
        return value

    def clean_exchange_rate_at_issue(self):
        return positive(self.cleaned_data['exchange_rate_at_issue'])

    def save(self, commit=True):
        note = super().save(commit=False)
        note.claim_id = note.claim_id or uuid.uuid4()
        note.insurer_id = note.insurer_id or uuid.uuid4()
        total = note.invoice_amount + (note.vat_amount or ZERO)
        note.total_amount = total
        note.base_currency_amount = (total * note.exchange_rate_at_issue).quantize(Decimal('0.01'))
        note.ugx_amount_efris = note.base_currency_amount
        note.balance_due = total - (note.amount_paid or ZERO)
        if commit:
            note.save()
        return note


class PaymentForm(forms.Form):
    amount_received_foreign = forms.DecimalField(label='Monto recibido', max_digits=18, decimal_places=2)
    exchange_rate = forms.DecimalField(
        label='Tasa de cambio hoy',
        max_digits=18,
        decimal_places=6,
        help_text='Para calcular la ganancia o pérdida cambiaria.',
    )
    payment_date = forms.DateField(label='Fecha del pago', widget=DATE)
    payment_method = forms.ChoiceField(
        label='Método', choices=spanish([('bank_transfer', ''), ('cheque', ''), ('cash', ''), ('mobile_money', '')])
    )
    bank_reference = forms.CharField(label='Referencia bancaria', required=False, max_length=100)
    wht_deducted = forms.BooleanField(label='Se retuvo impuesto (WHT)', required=False)
    wht_amount = forms.DecimalField(
        label='Monto retenido', required=False, min_value=0, max_digits=18, decimal_places=2
    )
    wht_cert_number = forms.CharField(label='N.º de certificado WHT', required=False, max_length=100)
    efris_receipt_ref = forms.CharField(label='Referencia de recibo EFRIS', required=False, max_length=100)

    def __init__(self, *args, fee_note, **kwargs):
        self.fee_note = fee_note
        super().__init__(*args, **kwargs)
        self.initial.setdefault('payment_date', timezone.localdate())
        self.initial.setdefault('exchange_rate', fee_note.exchange_rate_at_issue)
        self.initial.setdefault('amount_received_foreign', fee_note.balance_due)

    def clean_amount_received_foreign(self):
        value = positive(self.cleaned_data['amount_received_foreign'], 'El monto debe ser mayor que cero.')
        if value > self.fee_note.balance_due:
            raise forms.ValidationError(f'No puede superar el saldo pendiente ({self.fee_note.balance_due:,.2f}).')
        return value

    def clean_exchange_rate(self):
        return positive(self.cleaned_data['exchange_rate'])

    def clean(self):
        data = super().clean()
        if data.get('wht_deducted'):
            if not data.get('wht_amount'):
                self.add_error('wht_amount', 'Indica el monto retenido.')
            if not data.get('wht_cert_number'):
                self.add_error('wht_cert_number', 'Indica el número de certificado.')
        return data

    def payload(self):
        data = dict(self.cleaned_data)
        data['payment_currency'] = self.fee_note.invoice_currency
        data['wht_amount'] = data.get('wht_amount') or ZERO
        return data


class ReminderForm(forms.ModelForm):
    class Meta:
        model = FeeNoteReminder
        fields = ('reminder_type', 'sent_to')
        labels = {'reminder_type': 'Tipo', 'sent_to': 'Enviado a'}

    def __init__(self, *args, fee_note=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['reminder_type'] = forms.ChoiceField(
            label='Tipo', choices=[('friendly', 'Amistoso'), ('firm', 'Firme'), ('final', 'Final')]
        )
        self.fields['sent_to'] = forms.EmailField(label='Enviado a')
        if fee_note is not None:
            self.initial.setdefault('sent_to', fee_note.insurer_email)


# --------------------------------------------------------------------------- nomina


class EmployeeForm(TenantModelForm):
    class Meta:
        model = EmployeePayrollProfile
        fields = (
            'user',
            'employee_number',
            'tin_number',
            'nssf_number',
            'bank_name',
            'bank_account_number',
            'gross_salary',
            'start_date',
            'end_date',
            'is_active',
        )
        labels = {
            'user': 'Usuario del sistema',
            'employee_number': 'N.º de empleado',
            'tin_number': 'TIN',
            'nssf_number': 'N.º NSSF',
            'bank_name': 'Banco',
            'bank_account_number': 'N.º de cuenta',
            'gross_salary': 'Salario bruto mensual',
            'start_date': 'Fecha de ingreso',
            'end_date': 'Fecha de salida',
            'is_active': 'Empleado activo',
        }
        widgets = {'start_date': DATE, 'end_date': DATE}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['user'].queryset = (
            User.objects.filter(tenant_roles__tenant=self.tenant, tenant_roles__is_active=True)
            .distinct()
            .order_by('username')
        )
        self.fields['user'].help_text = 'Debe tener un rol en esta empresa.'

    def clean_gross_salary(self):
        return positive(self.cleaned_data['gross_salary'])

    def clean_employee_number(self):
        number = self.cleaned_data['employee_number']
        clash = EmployeePayrollProfile.objects.filter(tenant=self.tenant, employee_number=number)
        if self.instance.pk:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise forms.ValidationError('Ya existe un empleado con ese número en esta empresa.')
        return number

    def clean(self):
        data = super().clean()
        start, end = data.get('start_date'), data.get('end_date')
        if start and end and end < start:
            self.add_error('end_date', 'La salida no puede ser anterior al ingreso.')
        return data


class AllowanceForm(forms.ModelForm):
    class Meta:
        model = EmployeeAllowance
        fields = ('allowance_type', 'amount', 'is_taxable')
        labels = {'allowance_type': 'Tipo', 'amount': 'Monto mensual', 'is_taxable': 'Gravable'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['allowance_type'].choices = spanish(self.fields['allowance_type'].choices)
        self.initial.setdefault('is_taxable', True)

    def clean_amount(self):
        return positive(self.cleaned_data['amount'])


class PayrollPeriodForm(forms.Form):
    month = forms.TypedChoiceField(
        label='Mes',
        coerce=int,
        choices=[
            (i, n)
            for i, n in enumerate(
                [
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
                ],
                start=1,
            )
        ],
    )
    year = forms.IntegerField(label='Año', min_value=2000, max_value=2100)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        today = timezone.localdate()
        self.initial.setdefault('month', today.month)
        self.initial.setdefault('year', today.year)


# --------------------------------------------------------------------------- tesoreria


class BankAccountForm(TenantModelForm):
    class Meta:
        model = BankAccount
        fields = (
            'account_name',
            'bank_name',
            'account_number',
            'currency',
            'account_type',
            'opening_balance',
            'is_active',
        )
        labels = {
            'account_name': 'Nombre de la cuenta',
            'bank_name': 'Banco',
            'account_number': 'N.º de cuenta',
            'account_type': 'Tipo',
            'opening_balance': 'Saldo inicial',
            'is_active': 'Cuenta activa',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.use_currency('currency')
        self.translate('account_type')
        if self.instance.pk:  # el saldo inicial no se cambia: el saldo actual ya depende de el
            self.fields['opening_balance'].disabled = True
            self.fields['currency'].disabled = True


class ReconciliationForm(TenantModelForm):
    class Meta:
        model = BankReconciliation
        fields = (
            'bank_account',
            'period_month',
            'period_year',
            'opening_balance',
            'closing_balance_per_bank',
            'closing_balance_per_system',
            'notes',
        )
        labels = {
            'bank_account': 'Cuenta',
            'period_month': 'Mes',
            'period_year': 'Año',
            'opening_balance': 'Saldo inicial',
            'closing_balance_per_bank': 'Saldo final según el banco',
            'closing_balance_per_system': 'Saldo final según el sistema',
            'notes': 'Notas',
        }
        widgets = {'notes': forms.Textarea(attrs={'rows': 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['bank_account'].queryset = BankAccount.objects.filter(tenant=self.tenant, is_active=True)
        self.fields['period_month'].widget.attrs.update(min=1, max=12)
        self.fields['closing_balance_per_system'].help_text = 'Se propone el saldo actual de la cuenta.'
        today = timezone.localdate()
        self.initial.setdefault('period_month', today.month)
        self.initial.setdefault('period_year', today.year)
        if self.instance.pk:
            self.fields['bank_account'].disabled = True

    def clean_period_month(self):
        value = self.cleaned_data['period_month']
        if not 1 <= value <= 12:
            raise forms.ValidationError('El mes debe estar entre 1 y 12.')
        return value

    def clean(self):
        data = super().clean()
        account, month, year = data.get('bank_account'), data.get('period_month'), data.get('period_year')
        if account and month and year:
            clash = BankReconciliation.objects.filter(bank_account=account, period_month=month, period_year=year)
            if self.instance.pk:
                clash = clash.exclude(pk=self.instance.pk)
            if clash.exists():
                self.add_error('period_month', 'Ya hay una conciliación de esa cuenta para ese periodo.')
        return data


class PettyCashForm(TenantModelForm):
    class Meta:
        model = PettyCashTransaction
        fields = ('bank_account', 'transaction_type', 'amount', 'description', 'transaction_date', 'reference')
        labels = {
            'bank_account': 'Caja',
            'transaction_type': 'Tipo',
            'amount': 'Monto',
            'description': 'Descripción',
            'transaction_date': 'Fecha',
            'reference': 'Referencia',
        }
        widgets = {'transaction_date': DATE}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['bank_account'].queryset = BankAccount.objects.filter(
            tenant=self.tenant, is_active=True, account_type='petty_cash'
        )
        self.translate('transaction_type')
        self.initial.setdefault('transaction_date', timezone.localdate())

    def clean_amount(self):
        return positive(self.cleaned_data['amount'])

    def clean(self):
        data = super().clean()
        account, kind, amount = data.get('bank_account'), data.get('transaction_type'), data.get('amount')
        if account and kind == 'withdrawal' and amount and amount > account.current_balance:
            self.add_error('amount', f'Saldo insuficiente en la caja ({account.current_balance:,.2f}).')
        return data


class ChequeForm(TenantModelForm):
    class Meta:
        model = Cheque
        fields = (
            'bank_account',
            'cheque_type',
            'cheque_number',
            'amount',
            'payee_payer',
            'issue_date',
            'fee_note',
            'notes',
        )
        labels = {
            'bank_account': 'Cuenta',
            'cheque_type': 'Tipo',
            'cheque_number': 'N.º de cheque',
            'amount': 'Monto',
            'payee_payer': 'Beneficiario / ordenante',
            'issue_date': 'Fecha',
            'fee_note': 'Nota de honorarios (opcional)',
            'notes': 'Notas',
        }
        widgets = {'issue_date': DATE, 'notes': forms.Textarea(attrs={'rows': 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['bank_account'].queryset = BankAccount.objects.filter(tenant=self.tenant, is_active=True).exclude(
            account_type='petty_cash'
        )
        self.fields['fee_note'].queryset = FeeNote.objects.filter(tenant=self.tenant, is_void=False)
        self.fields['fee_note'].required = False
        self.translate('cheque_type')
        self.initial.setdefault('issue_date', timezone.localdate())

    def clean_amount(self):
        return positive(self.cleaned_data['amount'])

    def clean(self):
        data = super().clean()
        account, number = data.get('bank_account'), data.get('cheque_number')
        if account and number:
            clash = Cheque.objects.filter(bank_account=account, cheque_number=number)
            if clash.exists():
                self.add_error('cheque_number', 'Ya existe un cheque con ese número en esa cuenta.')
        return data


# --------------------------------------------------------------------------- contabilidad


class AccountForm(TenantModelForm):
    class Meta:
        model = Account
        fields = ('code', 'name', 'category', 'parent', 'is_active')
        labels = {
            'code': 'Código',
            'name': 'Nombre',
            'category': 'Categoría',
            'parent': 'Cuenta padre (opcional)',
            'is_active': 'Cuenta activa',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        parents = Account.objects.filter(tenant=self.tenant)
        if self.instance.pk:
            parents = parents.exclude(pk=self.instance.pk)
        self.fields['parent'].queryset = parents
        self.fields['parent'].required = False
        self.translate('category')

    def clean_code(self):
        code = self.cleaned_data['code'].strip()
        clash = Account.objects.filter(tenant=self.tenant, code=code)
        if self.instance.pk:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise forms.ValidationError('Ya existe una cuenta con ese código en esta empresa.')
        return code


class JournalEntryForm(forms.ModelForm):
    class Meta:
        model = JournalEntry
        fields = ('entry_date', 'reference', 'description')
        labels = {'entry_date': 'Fecha', 'reference': 'Referencia', 'description': 'Descripción'}
        widgets = {'entry_date': DATE, 'description': forms.Textarea(attrs={'rows': 2})}

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.initial.setdefault('entry_date', timezone.localdate())


class JournalLineForm(forms.ModelForm):
    account = forms.ModelChoiceField(queryset=Account.objects.none(), label='Cuenta')

    class Meta:
        model = JournalLine
        fields = ('account', 'debit_amount', 'credit_amount', 'description')
        labels = {'debit_amount': 'Debe', 'credit_amount': 'Haber', 'description': 'Detalle'}

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['account'].queryset = Account.objects.filter(tenant=tenant, is_active=True).order_by('code')
        self.fields['account'].empty_label = 'Elige cuenta'
        self.fields['description'].widget = forms.TextInput()
        self.fields['description'].required = False
        for name in ('debit_amount', 'credit_amount'):
            self.fields[name].required = False
            if not self.instance.pk:  # el 0 por defecto del modelo haria que toda fila vacia cuente como modificada
                self.initial[name] = None

    def clean(self):
        data = super().clean()
        if not self.has_changed() or self.cleaned_data.get('DELETE'):
            return data
        debit = data.get('debit_amount') or ZERO
        credit = data.get('credit_amount') or ZERO
        if debit < 0 or credit < 0:
            raise forms.ValidationError('Los montos no pueden ser negativos.')
        if (debit > 0) == (credit > 0):
            raise forms.ValidationError('Cada línea debe tener un monto en el Debe o en el Haber, no en ambos.')
        data['debit_amount'], data['credit_amount'] = debit, credit
        return data


class BaseJournalFormSet(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        lines = [
            f.cleaned_data
            for f in self.forms
            if f.has_changed() and f.cleaned_data and not f.cleaned_data.get('DELETE')
        ]
        if len(lines) < 2:
            raise forms.ValidationError('Un asiento necesita al menos dos líneas.')
        debit = sum((line['debit_amount'] for line in lines), ZERO)
        credit = sum((line['credit_amount'] for line in lines), ZERO)
        if debit != credit:
            raise forms.ValidationError(f'El asiento no cuadra: Debe {debit:,.2f} ≠ Haber {credit:,.2f}.')


JournalLineFormSet = inlineformset_factory(
    JournalEntry,
    JournalLine,
    form=JournalLineForm,
    formset=BaseJournalFormSet,
    extra=4,
    can_delete=False,
)


class DateRangeForm(forms.Form):
    start_date = forms.DateField(label='Desde', widget=DATE)
    end_date = forms.DateField(label='Hasta', widget=DATE)

    def clean(self):
        data = super().clean()
        if data.get('start_date') and data.get('end_date') and data['end_date'] < data['start_date']:
            self.add_error('end_date', 'La fecha final no puede ser anterior a la inicial.')
        return data
