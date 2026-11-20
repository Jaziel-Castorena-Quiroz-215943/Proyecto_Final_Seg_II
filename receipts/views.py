import json
import logging
import uuid

from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_safe

from accounts.models import SecurityEvent, User
from orders.access import roles_required

from .crypto import InvalidReceipt, ReceiptConfigurationError, verify_envelope
from .forms import VerifyReceiptForm
from .models import Receipt
from .services import verify_stored_receipt

logger = logging.getLogger(__name__)
receipt_roles = roles_required(
    User.Role.CLIENTE, User.Role.OPERADOR, denied_kind=SecurityEvent.Kind.RECEIPT_ACCESS_DENIED,
)


def accessible_receipt(request, pk):
    receipts = Receipt.objects.select_related('payment__order')
    if request.user.role == User.Role.CLIENTE:
        receipts = receipts.filter(payment__order__user=request.user)
    receipt = receipts.filter(pk=pk).first()
    if receipt is None:
        SecurityEvent.objects.create(kind=SecurityEvent.Kind.RECEIPT_ACCESS_DENIED, user=request.user)
        raise Http404
    return receipt


def invalid_response(request):
    SecurityEvent.objects.create(kind=SecurityEvent.Kind.RECEIPT_INVALID, user=request.user)
    return HttpResponse('El comprobante no es válido.', status=400)


def configuration_response():
    logger.exception('No se pudo verificar el comprobante por configuración de claves.')
    return HttpResponse('No se pudo verificar el comprobante. Inténtalo más tarde.', status=503)


@receipt_roles
@never_cache
@require_safe
def detail(request, pk):
    receipt = accessible_receipt(request, pk)
    try:
        envelope = verify_stored_receipt(receipt)
    except InvalidReceipt:
        return invalid_response(request)
    except ReceiptConfigurationError:
        return configuration_response()
    return render(request, 'receipts/detail.html', {'receipt': receipt, 'body': envelope['body']})


@receipt_roles
@never_cache
@require_safe
def document(request, pk):
    receipt = accessible_receipt(request, pk)
    try:
        envelope = verify_stored_receipt(receipt)
    except InvalidReceipt:
        return invalid_response(request)
    except ReceiptConfigurationError:
        return configuration_response()
    return JsonResponse(envelope, json_dumps_params={'ensure_ascii': False})


def reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Clave JSON duplicada.')
        result[key] = value
    return result


@receipt_roles
@never_cache
@require_http_methods(['GET', 'POST'])
def verify(request):
    form = VerifyReceiptForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST':
        if not form.is_valid():
            return invalid_response(request)
        try:
            envelope = json.loads(form.cleaned_data['document'], object_pairs_hook=reject_duplicate_keys)
            body = verify_envelope(envelope)
            if not isinstance(body.get('receipt_id'), str):
                raise InvalidReceipt('Identificador de comprobante inválido.')
            receipt_id = uuid.UUID(body['receipt_id'])
        except (ValueError, TypeError, RecursionError, InvalidReceipt):
            return invalid_response(request)
        except ReceiptConfigurationError:
            return configuration_response()
        receipt = accessible_receipt(request, receipt_id)
        try:
            if verify_stored_receipt(receipt) != envelope:
                raise InvalidReceipt('El comprobante no coincide con el original.')
        except InvalidReceipt:
            return invalid_response(request)
        except ReceiptConfigurationError:
            return configuration_response()
        SecurityEvent.objects.create(kind=SecurityEvent.Kind.RECEIPT_VERIFIED, user=request.user)
        return render(request, 'receipts/verify.html', {'form': form, 'verified': True, 'receipt': receipt})
    return render(request, 'receipts/verify.html', {'form': form})
