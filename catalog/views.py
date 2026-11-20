from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_safe

from accounts.models import User

from .forms import ProductForm
from .models import Product


def operator_required(view):
    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_active or request.user.role != User.Role.OPERADOR:
            raise PermissionDenied
        return view(request, *args, **kwargs)
    return wrapped


@require_safe
def home(request):
    return render(request, 'catalog/home.html')


@require_safe
def product_list(request):
    products = Product.objects.filter(status=Product.Status.PUBLISHED)
    return render(request, 'catalog/list.html', {'products': products})


@require_safe
def product_detail(request, pk):
    product = get_object_or_404(Product, pk=pk, status=Product.Status.PUBLISHED)
    return render(request, 'catalog/detail.html', {'product': product})


@operator_required
@require_safe
def manage(request):
    return render(request, 'catalog/manage.html', {'products': Product.objects.all()})


@operator_required
@require_http_methods(['GET', 'POST'])
def product_create(request):
    form = ProductForm(
        request.POST if request.method == 'POST' else None,
        request.FILES if request.method == 'POST' else None,
    )
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Producto creado.')
        return redirect('catalog:manage')
    return render(request, 'catalog/product_form.html', {'form': form, 'title': 'Crear producto'})


@operator_required
@require_http_methods(['GET', 'POST'])
def product_edit(request, pk):
    product = get_object_or_404(Product, pk=pk)
    form = ProductForm(
        request.POST if request.method == 'POST' else None,
        request.FILES if request.method == 'POST' else None,
        instance=product,
    )
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Producto actualizado.')
        return redirect('catalog:manage')
    return render(request, 'catalog/product_form.html', {
        'form': form, 'title': 'Editar producto', 'product': product,
    })
