from django import template

from panel.forms import CATEGORY_LABELS

register = template.Library()

EXPENSE_STATUS = {'pending': 'Pendiente', 'approved': 'Aprobado', 'paid': 'Pagado', 'rejected': 'Rechazado'}
MOVEMENT_TYPES = {'contribution': 'Aporte', 'return': 'Rendimiento', 'withdrawal': 'Retiro', 'fee': 'Comisión'}


@register.filter
def expense_status(value):
    return EXPENSE_STATUS.get(value, value)


@register.filter
def category_es(value):
    return CATEGORY_LABELS.get(value, value)


@register.filter
def movement_es(value):
    return MOVEMENT_TYPES.get(value, value)
