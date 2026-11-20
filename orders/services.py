import uuid

from django.core import signing
from django.db import transaction

from accounts.models import SecurityEvent
from cart.models import Cart
from cart.services import cart_total, get_cart, quote_data, read_quote
from catalog.models import Product

from .models import Order, OrderItem, SimulatedPayment


class OrderConflict(Exception):
    pass


@transaction.atomic
def checkout(user, key, signed_quote):
    previous = Order.objects.filter(user=user, checkout_key=key).first()
    if previous:
        return previous
    cart = get_cart(user)
    cart = Cart.objects.select_for_update().get(pk=cart.pk)
    previous = Order.objects.filter(user=user, checkout_key=key).first()
    if previous:
        return previous
    if cart.checkout_key != key:
        raise OrderConflict('El carrito ha cambiado. Actualiza la página.')
    ids = list(cart.items.order_by('product_id').values_list('product_id', flat=True))
    products = list(Product.objects.select_for_update().filter(pk__in=ids).order_by('pk'))
    try:
        quoted = read_quote(signed_quote)
    except signing.BadSignature as exc:
        raise OrderConflict('La cotización no es válida o ha caducado.') from exc
    if not products or len(products) != len(ids) or any(p.status != Product.Status.PUBLISHED for p in products):
        raise OrderConflict('El carrito está vacío o contiene productos no disponibles.')
    if quoted != quote_data(cart, products):
        raise OrderConflict('El carrito o los precios cambiaron. Actualiza la página.')
    updated = Cart.objects.filter(pk=cart.pk, checkout_key=key).update(checkout_key=uuid.uuid4())
    if updated != 1:
        raise OrderConflict('El carrito ya fue procesado. Actualiza la página.')
    order = Order.objects.create(user=user, checkout_key=key, total=cart_total(products))
    OrderItem.objects.bulk_create([
        OrderItem(
            order=order, product=product, product_name=product.name, unit_price=product.price,
            pdf_name=product.pdf.name, pdf_sha256=product.sha256,
        )
        for product in products
    ])
    cart.items.all().delete()
    SecurityEvent.objects.create(kind=SecurityEvent.Kind.ORDER_CREATED, user=user)
    return order


@transaction.atomic
def simulate_payment(order, result):
    if result not in SimulatedPayment.Result.values:
        raise ValueError('Resultado de pago simulado no válido.')
    status = Order.Status.PAID if result == SimulatedPayment.Result.SUCCESS else Order.Status.FAILED
    changed = Order.objects.filter(pk=order.pk, status=Order.Status.PENDING).update(status=status)
    if not changed:
        payment = SimulatedPayment.objects.filter(order=order).first()
        if payment and payment.result == result and Order.objects.filter(pk=order.pk, status=status).exists():
            return
        raise OrderConflict('La orden ya tiene otro resultado de pago.')
    if SimulatedPayment.objects.filter(order=order).exists():
        raise OrderConflict('La orden tiene un pago inconsistente y requiere revisión.')
    payment = SimulatedPayment.objects.create(order=order, result=result)
    if status == Order.Status.PAID:
        from receipts.services import issue_receipt
        issue_receipt(payment)
    kind = SecurityEvent.Kind.PAYMENT_SUCCEEDED if status == Order.Status.PAID else SecurityEvent.Kind.PAYMENT_FAILED
    SecurityEvent.objects.create(kind=kind, user=order.user)
