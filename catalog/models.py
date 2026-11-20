from decimal import Decimal
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import FileSystemStorage
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.deconstruct import deconstructible

from .validators import inspect_pdf


@deconstructible
class PrivateCatalogStorage(FileSystemStorage):
    def __init__(self):
        super().__init__(
            location=settings.PRIVATE_CATALOG_ROOT,
            file_permissions_mode=0o600,
            directory_permissions_mode=0o700,
        )

    def url(self, name):
        raise ValueError('Los archivos del catálogo no tienen URL pública.')


def private_pdf_path(instance, filename):
    return f'{uuid4().hex}.pdf'


class Product(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Borrador'
        PUBLISHED = 'PUBLISHED', 'Publicado'
        ARCHIVED = 'ARCHIVED', 'Archivado'

    name = models.CharField('nombre', max_length=200)
    description = models.TextField('descripción')
    price = models.DecimalField('precio', max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0'))])
    status = models.CharField('estado', max_length=10, choices=Status.choices, default=Status.DRAFT)
    pdf = models.FileField('archivo PDF', upload_to=private_pdf_path, storage=PrivateCatalogStorage())
    sha256 = models.CharField('SHA-256', max_length=64, editable=False)

    class Meta:
        ordering = ['name', 'pk']
        constraints = [
            models.CheckConstraint(condition=models.Q(price__gte=0), name='catalog_product_price_nonnegative'),
            models.CheckConstraint(
                condition=models.Q(status__in=['DRAFT', 'PUBLISHED', 'ARCHIVED']),
                name='catalog_product_status_valid',
            ),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.pdf:
            raise ValidationError({'pdf': 'Debes proporcionar un archivo PDF.'})
        if not self.pdf._committed:
            update_fields = kwargs.get('update_fields')
            if update_fields is not None and 'pdf' not in update_fields:
                raise ValueError('update_fields debe incluir pdf al cambiar el archivo.')
            self.sha256 = inspect_pdf(self.pdf)
            if update_fields is not None:
                kwargs['update_fields'] = set(update_fields) | {'sha256'}
        elif self._state.adding:
            raise ValidationError({'pdf': 'Debes proporcionar un archivo PDF nuevo.'})
        return super().save(*args, **kwargs)
