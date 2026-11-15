from django import forms
from django.forms import inlineformset_factory

from finance.budgets.models import Budget, BudgetLine
from finance.expenses.models import Expense
from finance.investments.models import Investment, InvestmentMovement

CATEGORY_CHOICES = [
    ('rent', 'Alquiler'),
    ('internet', 'Internet'),
    ('fuel', 'Combustible'),
    ('audit_fees', 'Honorarios de auditoría'),
    ('utilities', 'Servicios'),
    ('office_supplies', 'Insumos de oficina'),
    ('travel', 'Viajes'),
    ('other', 'Otros'),
]
CATEGORY_LABELS = dict(CATEGORY_CHOICES)
CURRENCIES = [('USD', 'USD'), ('EUR', 'EUR'), ('VES', 'VES'), ('COP', 'COP'), ('UGX', 'UGX')]
DATE = forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d')


def _currency_field(current=None):
    choices = list(CURRENCIES)
    if current and current not in dict(choices):
        choices.append((current, current))
    return forms.ChoiceField(choices=choices, label='Moneda')


class PanelForm(forms.ModelForm):
    """Formulario con la empresa fija: valida unicidad y moneda sin exponer el campo."""

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)
        if 'currency' in self.fields:
            self.fields['currency'] = _currency_field(self.instance.currency if self.instance.pk else None)
            if not self.instance.pk:
                # El valor por defecto del modelo (UGX) pisaria el initial del campo: se fija aqui.
                self.initial['currency'] = 'USD'


class BudgetForm(PanelForm):
    class Meta:
        model = Budget
        fields = ('name', 'fiscal_year', 'period_start', 'period_end', 'currency', 'notes')
        labels = {'name': 'Nombre', 'fiscal_year': 'Año fiscal', 'period_start': 'Inicio del periodo',
                  'period_end': 'Fin del periodo', 'notes': 'Notas'}
        widgets = {'period_start': DATE, 'period_end': DATE, 'notes': forms.Textarea(attrs={'rows': 3})}

    def clean(self):
        data = super().clean()
        start, end = data.get('period_start'), data.get('period_end')
        if start and end and end < start:
            self.add_error('period_end', 'El fin del periodo no puede ser anterior al inicio.')
        name, year = data.get('name'), data.get('fiscal_year')
        if self.tenant and name and year:
            clash = Budget.objects.filter(tenant=self.tenant, name=name, fiscal_year=year)
            if self.instance.pk:
                clash = clash.exclude(pk=self.instance.pk)
            if clash.exists():
                self.add_error('name', 'Ya existe un presupuesto con ese nombre y año en esta empresa.')
        return data


class BudgetLineForm(forms.ModelForm):
    # La opcion vacia evita que las filas en blanco cuenten como "modificadas".
    category = forms.ChoiceField(choices=[('', 'Elige categoría')] + CATEGORY_CHOICES, label='Categoría')

    class Meta:
        model = BudgetLine
        fields = ('category', 'planned_amount', 'notes')
        labels = {'planned_amount': 'Monto planificado', 'notes': 'Nota'}

    def clean_planned_amount(self):
        value = self.cleaned_data['planned_amount']
        if value <= 0:
            raise forms.ValidationError('Debe ser mayor que cero.')
        return value


BudgetLineFormSet = inlineformset_factory(
    Budget, BudgetLine, form=BudgetLineForm, extra=0, can_delete=True,
)
BudgetLineFormSetNew = inlineformset_factory(
    Budget, BudgetLine, form=BudgetLineForm, extra=3, can_delete=False,
)


class InvestmentForm(PanelForm):
    class Meta:
        model = Investment
        fields = ('name', 'asset_type', 'institution', 'currency', 'initial_amount', 'start_date',
                  'maturity_date', 'expected_return_rate', 'status', 'notes')
        labels = {'name': 'Nombre', 'asset_type': 'Tipo', 'institution': 'Institución',
                  'initial_amount': 'Monto inicial', 'start_date': 'Fecha de inicio',
                  'maturity_date': 'Fecha de vencimiento', 'expected_return_rate': 'Rendimiento anual esperado (%)',
                  'status': 'Estado', 'notes': 'Notas'}
        widgets = {'start_date': DATE, 'maturity_date': DATE, 'notes': forms.Textarea(attrs={'rows': 3})}

    def clean_initial_amount(self):
        value = self.cleaned_data['initial_amount']
        if value <= 0:
            raise forms.ValidationError('Debe ser mayor que cero.')
        return value

    def clean(self):
        data = super().clean()
        start, maturity = data.get('start_date'), data.get('maturity_date')
        if start and maturity and maturity < start:
            self.add_error('maturity_date', 'El vencimiento no puede ser anterior al inicio.')
        return data


class MovementForm(forms.ModelForm):
    class Meta:
        model = InvestmentMovement
        fields = ('movement_type', 'amount', 'movement_date', 'notes')
        labels = {'movement_type': 'Tipo', 'amount': 'Monto', 'movement_date': 'Fecha', 'notes': 'Nota'}
        widgets = {'movement_date': DATE}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Sin opcion "---------": el primer tipo queda seleccionado.
        self.fields['movement_type'].choices = [c for c in self.fields['movement_type'].choices if c[0]]

    def clean_amount(self):
        value = self.cleaned_data['amount']
        if value <= 0:
            raise forms.ValidationError('El monto debe ser mayor que cero.')
        return value


class ExpenseForm(PanelForm):
    class Meta:
        model = Expense
        fields = ('description', 'category', 'amount', 'currency', 'expense_date', 'notes')
        labels = {'description': 'Descripción', 'category': 'Categoría', 'amount': 'Monto',
                  'expense_date': 'Fecha', 'notes': 'Notas'}
        widgets = {'expense_date': DATE, 'notes': forms.Textarea(attrs={'rows': 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'] = forms.ChoiceField(choices=CATEGORY_CHOICES, label='Categoría')

    def clean_amount(self):
        value = self.cleaned_data['amount']
        if value <= 0:
            raise forms.ValidationError('El monto debe ser mayor que cero.')
        return value
