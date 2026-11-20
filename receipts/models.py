import uuid

from django.db import models


class Receipt(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payment = models.OneToOneField('orders.SimulatedPayment', on_delete=models.PROTECT, related_name='receipt')
    key_id = models.CharField(max_length=64)
    body = models.TextField()
    sha256 = models.CharField(max_length=64)
    signature = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
