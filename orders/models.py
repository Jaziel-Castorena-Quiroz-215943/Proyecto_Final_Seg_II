from decimal import Decimal

from django.conf import settings
from django.db import models


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pendiente'
        PAID = 'PAID', 'Pagada'
        FAILED = 'FAILED', 'Fallida'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='orders')
    checkout_key = models.UUIDField(unique=True, editable=False)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    total = models.DecimalField(max_digits=20, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-pk']
        constraints = [
            models.CheckConstraint(condition=models.Q(total__gte=Decimal('0')), name='orders_total_nonnegative'),
            models.CheckConstraint(
                condition=models.Q(status__in=['PENDING', 'PAID', 'FAILED']),
                name='orders_status_valid',
            ),
        ]


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name='items')
    product = models.ForeignKey('catalog.Product', on_delete=models.PROTECT, related_name='order_items')
    product_name = models.CharField(max_length=200)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    pdf_name = models.CharField(max_length=100, null=True, blank=True, editable=False)
    pdf_sha256 = models.CharField(max_length=64, null=True, blank=True, editable=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['order', 'product'], name='orders_unique_product'),
            models.CheckConstraint(condition=models.Q(unit_price__gte=Decimal('0')), name='orders_price_nonnegative'),
        ]


class SimulatedPayment(models.Model):
    class Result(models.TextChoices):
        SUCCESS = 'SUCCESS', 'Éxito'
        FAILURE = 'FAILURE', 'Fallo'

    order = models.OneToOneField(Order, on_delete=models.PROTECT, related_name='payment')
    result = models.CharField(max_length=10, choices=Result.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(result__in=['SUCCESS', 'FAILURE']),
                name='orders_payment_result_valid',
            ),
        ]
