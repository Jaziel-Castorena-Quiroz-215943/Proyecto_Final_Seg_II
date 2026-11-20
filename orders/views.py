import logging

from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST, require_safe

from accounts.models import SecurityEvent, User
from receipts.crypto import ReceiptConfigurationError
from receipts.services import ReceiptIssuanceError

from .access import retry_on_sqlite_lock, roles_required
from .forms import CheckoutForm, PaymentForm
from .models import Order
from .services import OrderConflict, checkout, simulate_payment

logger = logging.getLogger(__name__)


def accessible_order(request, pk, *, owner_only=False):
    orders = Order.objects.all()
    if owner_only or request.user.role == User.Role.CLIENTE:
        orders = orders.filter(user=request.user)
    order = orders.filter(pk=pk).first()
    if order is None:
        SecurityEvent.objects.create(kind=SecurityEvent.Kind.ORDER_ACCESS_DENIED, user=request.user)
        raise Http404
    return order


@roles_required(User.Role.CLIENTE, User.Role.OPERADOR)
@never_cache
@require_safe
def order_list(request):
    orders = Order.objects.all()
    if request.user.role == User.Role.CLIENTE:
        orders = orders.filter(user=request.user)
    return render(request, 'orders/list.html', {'orders': orders})


@roles_required(User.Role.CLIENTE, User.Role.OPERADOR)
@never_cache
@require_safe
def order_detail(request, pk):
    order = accessible_order(request, pk)
    return render(request, 'orders/detail.html', {'order': order})


@roles_required(User.Role.CLIENTE)
@retry_on_sqlite_lock
@never_cache
@require_POST
def create(request):
    form = CheckoutForm(request.POST)
    if not form.is_valid():
        return HttpResponse('Cotización inválida.', status=400)
    try:
        order = checkout(request.user, form.cleaned_data['key'], form.cleaned_data['quote'])
    except OrderConflict as exc:
        SecurityEvent.objects.create(kind=SecurityEvent.Kind.ORDER_CONFLICT, user=request.user)
        return HttpResponse(str(exc), status=409)
    return redirect('orders:detail', pk=order.pk)


@roles_required(User.Role.CLIENTE)
@retry_on_sqlite_lock
@never_cache
@require_POST
def pay(request, pk):
    order = accessible_order(request, pk, owner_only=True)
    form = PaymentForm(request.POST)
    if not form.is_valid():
        return HttpResponse('Resultado de pago simulado inválido.', status=400)
    try:
        simulate_payment(order, form.cleaned_data['result'])
    except OrderConflict as exc:
        SecurityEvent.objects.create(kind=SecurityEvent.Kind.ORDER_CONFLICT, user=request.user)
        return HttpResponse(str(exc), status=409)
    except (ReceiptConfigurationError, ReceiptIssuanceError):
        logger.exception('No se pudo emitir el comprobante del pago simulado.')
        SecurityEvent.objects.create(kind=SecurityEvent.Kind.RECEIPT_ERROR, user=request.user)
        return HttpResponse('No se pudo emitir el comprobante. Inténtalo más tarde.', status=503)
    return redirect('orders:detail', pk=order.pk)
