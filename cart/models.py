import uuid

from django.conf import settings
from django.db import models


class Cart(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='cart')
    checkout_key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey('catalog.Product', on_delete=models.CASCADE, related_name='cart_items')

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['cart', 'product'], name='cart_unique_product'),
        ]
