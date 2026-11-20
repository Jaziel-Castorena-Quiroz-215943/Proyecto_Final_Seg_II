import json
import uuid
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from accounts.models import SecurityEvent
from orders.models import Order, SimulatedPayment

from .crypto import ALGORITHM, FORMAT, InvalidReceipt, canonical_json, sign_body, signing_key, verify_envelope
from .models import Receipt


class ReceiptIssuanceError(Exception):
    pass


def order_items(order):
    return [
        {'product_id': item.product_id, 'name': item.product_name, 'unit_price': format(item.unit_price, '.2f')}
        for item in order.items.order_by('product_id')
    ]


@transaction.atomic
def issue_receipt(payment):
    order = Order.objects.select_for_update().get(pk=payment.order_id)
    if order.status != Order.Status.PAID or payment.result != SimulatedPayment.Result.SUCCESS:
        raise ReceiptIssuanceError('El pago no está aprobado.')
    items = order_items(order)
    if not items or sum((Decimal(item['unit_price']) for item in items), Decimal('0.00')) != order.total:
        raise ReceiptIssuanceError('Los importes de la orden no son consistentes.')
    key_id, private = signing_key()
    receipt_id = uuid.uuid4()
    body = {
        'format': FORMAT,
        'algorithm': ALGORITHM,
        'key_id': key_id,
        'receipt_id': str(receipt_id),
        'order_id': order.pk,
        'user_id': order.user_id,
        'payment_id': payment.pk,
        'payment_type': 'SIMULATED',
        'payment_result': 'SUCCESS',
        'paid_at': payment.created_at.isoformat(),
        'issued_at': timezone.now().isoformat(),
        'total': format(order.total, '.2f'),
        'items': items,
    }
    digest, signature = sign_body(body, private)
    receipt = Receipt.objects.create(
        id=receipt_id, payment=payment, key_id=key_id,
        body=canonical_json(body), sha256=digest, signature=signature,
    )
    SecurityEvent.objects.create(kind=SecurityEvent.Kind.RECEIPT_ISSUED, user=order.user)
    return receipt


def receipt_envelope(receipt):
    try:
        body = json.loads(receipt.body)
        if receipt.body != canonical_json(body):
            raise InvalidReceipt('El contenido almacenado no es canónico.')
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise InvalidReceipt('Contenido almacenado inválido.') from exc
    return {'body': body, 'sha256': receipt.sha256, 'signature': receipt.signature}


def verify_stored_receipt(receipt):
    envelope = receipt_envelope(receipt)
    body = verify_envelope(envelope, trusted_record=True)
    try:
        payment = SimulatedPayment.objects.select_related('order').get(pk=receipt.payment_id)
    except SimulatedPayment.DoesNotExist as exc:
        raise InvalidReceipt('El pago asociado no existe.') from exc
    order = payment.order
    if (
        body.get('receipt_id') != str(receipt.pk)
        or body.get('key_id') != receipt.key_id
        or body.get('order_id') != order.pk
        or body.get('user_id') != order.user_id
        or body.get('payment_id') != payment.pk
        or body.get('payment_type') != 'SIMULATED'
        or body.get('payment_result') != 'SUCCESS'
        or body.get('paid_at') != payment.created_at.isoformat()
        or body.get('total') != format(order.total, '.2f')
        or body.get('items') != order_items(order)
        or payment.result != SimulatedPayment.Result.SUCCESS
        or order.status != Order.Status.PAID
    ):
        raise InvalidReceipt('El comprobante no coincide con la orden o el pago.')
    return envelope
