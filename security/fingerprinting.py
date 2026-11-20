import hashlib
import hmac
import re
import secrets

import pymupdf
from django.core.exceptions import SuspiciousFileOperation
from django.db import transaction

from accounts.models import SecurityEvent
from catalog.models import Product
from catalog.validators import MAX_PDF_SIZE
from orders.models import Order, OrderItem, SimulatedPayment

from .models import DownloadFingerprint

MARKER_NAME = '__platform_fingerprint_v1__'
TOKEN_PATTERN = re.compile(r'^[0-9a-f]{32}$')
MAX_MARKED_PDF_SIZE = 30 * 1024 * 1024


class FingerprintError(Exception):
    pass


class FingerprintAccessError(Exception):
    pass


def read_original(item):
    if not item.pdf_name or not item.pdf_sha256:
        raise FingerprintError('La orden no tiene una versión de PDF registrada.')
    if not re.fullmatch(r'[0-9a-f]{64}', item.pdf_sha256):
        raise FingerprintError('El resumen del PDF original no es válido.')
    storage = Product._meta.get_field('pdf').storage
    digest = hashlib.sha256()
    chunks = []
    size = 0
    try:
        with storage.open(item.pdf_name, 'rb') as original:
            for chunk in original.chunks():
                size += len(chunk)
                if size > MAX_PDF_SIZE:
                    raise FingerprintError('El PDF original supera el tamaño permitido.')
                digest.update(chunk)
                chunks.append(chunk)
    except (OSError, SuspiciousFileOperation) as exc:
        raise FingerprintError('El PDF original no está disponible.') from exc
    if not hmac.compare_digest(digest.hexdigest(), item.pdf_sha256):
        raise FingerprintError('El PDF original no coincide con la versión comprada.')
    return b''.join(chunks)


def watermark_pdf(original, token):
    if not TOKEN_PATTERN.fullmatch(token):
        raise ValueError('Identificador de huella inválido.')
    try:
        with pymupdf.open(stream=original, filetype='pdf') as document:
            if (
                not document.is_pdf or document.is_encrypted or document.needs_pass
                or (document.metadata and document.metadata.get('encryption'))
                or document.is_repaired or document.page_count == 0
            ):
                raise FingerprintError('El PDF original no es válido para personalizar.')
            if document.get_sigflags() > 0:
                raise FingerprintError('No se puede personalizar un PDF con firmas digitales.')
            if MARKER_NAME in document.embfile_names():
                raise FingerprintError('El PDF original ya contiene una marca reservada.')
            label = 'FPR-' + token
            unit_width = pymupdf.get_text_length(label, fontname='helv', fontsize=1)
            for page in document:
                if any(widget.field_type == pymupdf.PDF_WIDGET_TYPE_SIGNATURE for widget in (page.widgets() or ())):
                    raise FingerprintError('No se puede personalizar un PDF con campos de firma.')
                rect = page.cropbox
                font_size = min(7.0, rect.width / (unit_width + 2), rect.height / 12)
                if font_size <= 0:
                    raise FingerprintError('El tamaño de página no permite insertar la huella.')
                point = pymupdf.Point(font_size, rect.height - font_size)
                if page.insert_text(point, label, fontsize=font_size, fontname='helv', color=(0.35, 0.35, 0.35)) != 1:
                    raise FingerprintError('No se pudo insertar la huella visible.')
            document.embfile_add(MARKER_NAME, token.encode('ascii'))
            result = document.tobytes(garbage=4, deflate=True)
    except pymupdf.FileDataError as exc:
        raise FingerprintError('El PDF original no es válido.') from exc
    if len(result) > MAX_MARKED_PDF_SIZE:
        raise FingerprintError('El PDF personalizado supera el tamaño permitido.')
    return result


@transaction.atomic
def issue_download(user, item_id):
    item = OrderItem.objects.select_for_update().filter(pk=item_id, order__user=user).first()
    if item is None:
        raise FingerprintAccessError
    order = Order.objects.select_for_update().filter(pk=item.order_id, user=user, status=Order.Status.PAID).first()
    payment = SimulatedPayment.objects.select_for_update().filter(
        order_id=item.order_id, result=SimulatedPayment.Result.SUCCESS,
    ).first()
    if order is None or payment is None:
        raise FingerprintAccessError
    original = read_original(item)
    token = secrets.token_hex(16)
    result = watermark_pdf(original, token)
    DownloadFingerprint.objects.create(
        token=token, user=user, order_item=item, document_sha256=hashlib.sha256(result).hexdigest(),
    )
    SecurityEvent.objects.create(kind=SecurityEvent.Kind.DOWNLOAD_CREATED, user=user)
    return result


def extract_token(data):
    if not data.startswith(b'%PDF-') or len(data) > MAX_MARKED_PDF_SIZE:
        raise FingerprintError('El documento no es un PDF válido.')
    try:
        with pymupdf.open(stream=data, filetype='pdf') as document:
            if (
                not document.is_pdf or document.is_encrypted or document.needs_pass
                or document.is_repaired or MARKER_NAME not in document.embfile_names()
            ):
                raise FingerprintError('El PDF no contiene una huella recuperable.')
            if document.embfile_info(MARKER_NAME)['size'] != 32:
                raise FingerprintError('La huella tiene un formato inválido.')
            token = document.embfile_get(MARKER_NAME).decode('ascii')
    except (pymupdf.FileDataError, UnicodeDecodeError) as exc:
        raise FingerprintError('El PDF o su huella no son válidos.') from exc
    if not TOKEN_PATTERN.fullmatch(token):
        raise FingerprintError('La huella tiene un formato inválido.')
    return token


def identify_download(data):
    token = extract_token(data)
    download = DownloadFingerprint.objects.select_related('user', 'order_item__order', 'order_item__product').filter(
        token=token,
    ).first()
    if download is None or not hmac.compare_digest(download.document_sha256, hashlib.sha256(data).hexdigest()):
        raise FingerprintError('La huella no corresponde al documento emitido.')
    return download
