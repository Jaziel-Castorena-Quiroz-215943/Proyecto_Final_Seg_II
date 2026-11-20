from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST, require_safe

from accounts.models import User
from catalog.models import Product
from orders.access import retry_on_sqlite_lock, roles_required

from .models import Cart
from .services import add_product, cart_total, current_products, remove_product, sign_quote


@roles_required(User.Role.CLIENTE)
@never_cache
@require_safe
def detail(request):
    cart = Cart.objects.filter(user=request.user).first()
    products = current_products(cart) if cart else []
    available = all(product.status == Product.Status.PUBLISHED for product in products)
    return render(request, 'cart/detail.html', {
        'cart': cart, 'products': products, 'total': cart_total(products),
        'quote': sign_quote(cart, products) if cart else '', 'available': available,
    })


@roles_required(User.Role.CLIENTE)
@retry_on_sqlite_lock
@require_POST
def add(request, pk):
    if not add_product(request.user, pk):
        raise Http404
    return redirect('cart:detail')


@roles_required(User.Role.CLIENTE)
@retry_on_sqlite_lock
@require_POST
def remove(request, pk):
    remove_product(request.user, pk)
    return redirect('cart:detail')
