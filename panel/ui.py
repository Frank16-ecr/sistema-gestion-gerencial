"""Piezas de interfaz reutilizables: celdas de tabla, acciones, tarjetas y graficos genericos.

Las vistas arman diccionarios sencillos y las plantillas genericas (`generic_page.html`,
`_table.html`) los dibujan, asi cada pantalla nueva es corta y se ve igual que las demas.
"""
from decimal import Decimal

SPANISH = {
    # notas de honorarios
    'draft': 'Borrador', 'submitted': 'Enviada a EFRIS', 'stamped': 'Sellada EFRIS',
    'sent': 'Enviada a la aseguradora', 'partial': 'Pago parcial', 'paid': 'Pagada',
    'overdue_1': 'Vencida 30 días', 'overdue_2': 'Vencida 60 días', 'overdue_3': 'Vencida 90+ días', 'void': 'Anulada',
    # nomina, conciliaciones, cheques
    'approved': 'Aprobada', 'open': 'Abierta', 'locked': 'Cerrada', 'pending': 'Pendiente', 'cleared': 'Cobrado',
    'bounced': 'Rebotado', 'cancelled': 'Cancelado',
    # tipos
    'current': 'Corriente', 'savings': 'Ahorro', 'petty_cash': 'Caja chica',
    'withdrawal': 'Retiro', 'top_up': 'Reposición', 'receipt': 'Recibido', 'issued': 'Emitido',
    'bank_transfer': 'Transferencia', 'cheque': 'Cheque', 'cash': 'Efectivo', 'mobile_money': 'Dinero móvil',
    'asset': 'Activo', 'liability': 'Pasivo', 'equity': 'Patrimonio', 'income': 'Ingreso', 'expense': 'Gasto',
    'transport': 'Transporte', 'housing': 'Vivienda', 'medical': 'Médica', 'lunch': 'Alimentación', 'other': 'Otra',
    'friendly': 'Amistoso', 'firm': 'Firme', 'final': 'Final',
}
GOOD = {'paid', 'approved', 'cleared', 'open', 'income'}
BAD = {'overdue_1', 'overdue_2', 'overdue_3', 'bounced', 'void', 'cancelled'}
WARN = {'partial', 'pending', 'submitted'}
NAVY = {'sent', 'stamped', 'locked', 'receipt', 'issued'}


def es(value):
    return SPANISH.get(value, value)


def badge_class(status):
    if status in GOOD:
        return 'ok'
    if status in BAD:
        return 'bad'
    if status in WARN:
        return 'warn'
    if status in NAVY:
        return 'navy'
    return ''


def fmt(value, places=2):
    if value is None or value == '':
        return '—'
    return f'{Decimal(value):,.{places}f}'


def fdate(value):
    return value.strftime('%d/%m/%Y') if value else '—'


def cell(text='', *, href=None, badge=None, num=False, sort=None, sub=None, cls=''):
    """Una celda de tabla. `badge` es la clase del badge ('ok', 'bad', ...) y `text` su texto."""
    return {'text': text, 'href': href, 'badge': badge, 'num': num, 'sub': sub, 'cls': cls,
            'sort': sort if sort is not None else ''}


def status_cell(status, label=None):
    return cell(label or es(status), badge=badge_class(status) or 'muted', sort=status)


def money_cell(value, currency='', *, cls=''):
    return cell(f'{fmt(value)} {currency}'.strip(), num=True, sort=str(value if value is not None else 0), cls=cls)


def act(label, url, *, style='', confirm=None, prompt=None, next_url=None, method='post'):
    """Boton de accion: POST por defecto, o enlace si method='get'."""
    return {'label': label, 'url': url, 'style': style, 'confirm': confirm, 'prompt': prompt,
            'next': next_url, 'method': method}


def table(columns, rows, *, title=None, empty='No hay registros.', table_id='t', searchable=True, sub=None):
    """columns: [(etiqueta, {'num': True, 'sort': True})]. rows: [{'cells': [...], 'actions': [...]}]."""
    cols = [{'label': label, 'num': opts.get('num', False), 'sort': opts.get('sort', True)}
            for label, opts in ((c if isinstance(c, tuple) else (c, {})) for c in columns)]
    has_actions = any(row.get('actions') for row in rows)
    return {'id': table_id, 'title': title, 'columns': cols, 'rows': rows, 'empty': empty,
            'searchable': searchable and len(rows) > 5, 'has_actions': has_actions, 'sub': sub}


def kpi(label, value, note='', variant='', negative=False):
    return {'label': label, 'value': value, 'note': note, 'variant': variant, 'negative': negative}


def chart(dom_id, title, kind, labels, datasets, *, currency='', stacked=False, horizontal=False, height=''):
    """Grafico generico para Chart.js. datasets: [{'label', 'data', 'color': 'green|navy|fuchsia|...'}]."""
    return {
        'dom_id': dom_id, 'title': title, 'height': height,
        'data': {'type': kind, 'labels': labels, 'datasets': datasets, 'currency': currency,
                 'stacked': stacked, 'horizontal': horizontal},
    }


def f(value):
    """Decimal -> float para JSON de graficos."""
    return float(value or 0)
