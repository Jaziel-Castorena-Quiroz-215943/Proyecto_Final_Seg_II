from decimal import Decimal

from django.core import signing
from django.db import transaction

from catalog.models import Product

from .models import Cart, CartItem

QUOTE_SALT = 'cart.checkout.quote'
QUOTE_MAX_AGE = 900


def get_cart(user):
    cart, _ = Cart.objects.get_or_create(user=user)
    return cart


def quote_data(cart, products):
    return {
        'user': cart.user_id,
        'key': str(cart.checkout_key),
        'products': [[product.pk, product.name, str(product.price)] for product in products],
    }


def sign_quote(cart, products):
    return signing.dumps(quote_data(cart, products), salt=QUOTE_SALT, compress=True)


def read_quote(value):
    return signing.loads(value, salt=QUOTE_SALT, max_age=QUOTE_MAX_AGE)


def current_products(cart):
    ids = list(cart.items.order_by('product_id').values_list('product_id', flat=True))
    return list(Product.objects.filter(pk__in=ids).order_by('pk'))


def cart_total(products):
    return sum((product.price for product in products), Decimal('0.00'))


@transaction.atomic
def add_product(user, product_id):
    cart = get_cart(user)
    cart = Cart.objects.select_for_update().get(pk=cart.pk)
    product = Product.objects.select_for_update().filter(pk=product_id, status=Product.Status.PUBLISHED).first()
    if product is None:
        return False
    CartItem.objects.get_or_create(cart=cart, product=product)
    return True


@transaction.atomic
def remove_product(user, product_id):
    cart = get_cart(user)
    cart = Cart.objects.select_for_update().get(pk=cart.pk)
    CartItem.objects.filter(cart=cart, product_id=product_id).delete()
