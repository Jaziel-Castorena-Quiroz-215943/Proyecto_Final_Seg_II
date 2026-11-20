from django.conf import settings
from django.db import models


class DownloadFingerprint(models.Model):
    token = models.CharField(max_length=32, unique=True, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='pdf_downloads')
    order_item = models.ForeignKey('orders.OrderItem', on_delete=models.PROTECT, related_name='pdf_downloads')
    document_sha256 = models.CharField(max_length=64, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
