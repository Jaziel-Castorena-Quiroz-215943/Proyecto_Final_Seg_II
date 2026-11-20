import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError, OperationalError, close_old_connections
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from accounts.models import SecurityEvent
from cart.models import Cart, CartItem
from cart.services import current_products, get_cart, sign_quote
from catalog.models import Product
from receipts.models import Receipt
from receipts.test_helpers import ReceiptKeysMixin

from .models import Order, SimulatedPayment
from .services import OrderConflict, checkout, simulate_payment

User = get_user_model()


def product(name='Libro', price='12.50', status=Product.Status.PUBLISHED):
    item = Product(name=name, description='PDF', price=price, status=status, pdf='fixture.pdf', sha256='a' * 64)
    Product.objects.bulk_create([item])
    return item


@override_settings(ALLOWED_HOSTS=['testserver'])
class PurchaseTests(ReceiptKeysMixin, TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='cliente', email='cliente@example.com', password='Password-482!')
        self.other = User.objects.create_user(username='otro', email='otro@example.com', password='Password-482!')
        self.operator = User.objects.create_user(
            username='operador', email='operador@example.com', password='Password-482!', role=User.Role.OPERADOR,
        )
        self.admin = User.objects.create_superuser('admin', 'admin@example.com', 'Password-482!')
        self.product = product()
        self.client.force_login(self.user)

    def add(self, item=None):
        return self.client.post(reverse('cart:add', args=[(item or self.product).pk]))

    def quote(self):
        response = self.client.get(reverse('cart:detail'))
        return {'key': str(response.context['cart'].checkout_key), 'quote': response.context['quote']}

    def create_order(self):
        self.add()
        response = self.client.post(reverse('orders:checkout'), self.quote())
        self.assertEqual(response.status_code, 302)
        return Order.objects.latest('id')

    def test_cart_idempotency_price_snapshot_and_repurchase(self):
        self.add()
        self.add()
        self.assertEqual(CartItem.objects.count(), 1)
        data = self.quote()
        data.update({'price': '0.01', 'total': '0.01'})
        response = self.client.post(reverse('orders:checkout'), data)
        self.assertEqual(response.status_code, 302)
        order = Order.objects.get()
        self.assertEqual(order.total, Decimal('12.50'))
        self.assertEqual(order.items.get().unit_price, Decimal('12.50'))
        self.assertEqual(CartItem.objects.count(), 0)
        self.assertEqual(self.client.post(reverse('orders:checkout'), data).url, response.url)
        self.assertEqual(Order.objects.count(), 1)
        Product.objects.filter(pk=self.product.pk).update(price='99.00', name='Nombre nuevo')
        order.refresh_from_db()
        self.assertEqual(order.items.get().product_name, 'Libro')
        self.assertEqual(order.total, Decimal('12.50'))
        self.assertEqual(SecurityEvent.objects.filter(kind='ORDER_CREATED', user=self.user).count(), 1)
        self.add()
        new_response = self.client.post(reverse('orders:checkout'), self.quote())
        self.assertEqual(new_response.status_code, 302)
        self.assertEqual(Order.objects.count(), 2)
        self.assertEqual(Order.objects.latest('id').total, Decimal('99.00'))

    def test_stale_tampered_and_foreign_quotes_are_rejected(self):
        self.add()
        quote = self.quote()
        Product.objects.filter(pk=self.product.pk).update(price='19.99')
        self.assertEqual(self.client.post(reverse('orders:checkout'), quote).status_code, 409)
        self.assertFalse(Order.objects.exists())
        self.assertEqual(CartItem.objects.count(), 1)
        fresh = self.quote()
        fresh['quote'] += 'tampered'
        self.assertEqual(self.client.post(reverse('orders:checkout'), fresh).status_code, 409)
        fresh = self.quote()
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(reverse('orders:checkout'), fresh).status_code, 409)
        self.assertFalse(Order.objects.exists())
        self.assertEqual(SecurityEvent.objects.filter(kind='ORDER_CONFLICT').count(), 3)

    def test_unavailable_and_changed_cart_cannot_be_checked_out(self):
        self.add()
        quote = self.quote()
        Product.objects.filter(pk=self.product.pk).update(status=Product.Status.ARCHIVED)
        self.assertEqual(self.client.post(reverse('orders:checkout'), quote).status_code, 409)
        self.assertEqual(self.add().status_code, 404)
        self.client.post(reverse('cart:remove', args=[self.product.pk]))
        self.assertEqual(self.client.post(reverse('orders:checkout'), quote).status_code, 409)
        self.assertFalse(Order.objects.exists())

    def test_expired_quote_and_changed_cart_are_rejected(self):
        self.add()
        with patch('django.core.signing.TimestampSigner.timestamp', return_value='1'):
            expired = self.quote()
        self.assertEqual(self.client.post(reverse('orders:checkout'), expired).status_code, 409)
        quote = self.quote()
        another = product(name='Otro', price='3.00')
        self.add(another)
        self.assertEqual(self.client.post(reverse('orders:checkout'), quote).status_code, 409)
        self.assertFalse(Order.objects.exists())

    def test_payment_once_success_and_failure(self):
        order = self.create_order()
        url = reverse('orders:pay', args=[order.pk])
        self.assertEqual(self.client.post(url, {'result': 'SUCCESS', 'amount': '0.01'}).status_code, 302)
        self.assertEqual(self.client.post(url, {'result': 'SUCCESS'}).status_code, 302)
        self.assertEqual(self.client.post(url, {'result': 'FAILURE'}).status_code, 409)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAID)
        self.assertEqual(order.payment.result, SimulatedPayment.Result.SUCCESS)
        self.assertEqual(SimulatedPayment.objects.filter(order=order).count(), 1)
        self.assertEqual(Receipt.objects.filter(payment__order=order).count(), 1)
        self.assertEqual(SecurityEvent.objects.filter(kind='PAYMENT_SUCCEEDED').count(), 1)
        failed = self.create_order()
        failure_url = reverse('orders:pay', args=[failed.pk])
        self.assertEqual(self.client.post(failure_url, {'result': 'bad'}).status_code, 400)
        self.assertEqual(self.client.post(failure_url, {'result': 'FAILURE'}).status_code, 302)
        self.assertEqual(self.client.post(failure_url, {'result': 'FAILURE'}).status_code, 302)
        self.assertEqual(self.client.post(failure_url, {'result': 'SUCCESS'}).status_code, 409)
        failed.refresh_from_db()
        self.assertEqual(failed.status, Order.Status.FAILED)
        self.assertEqual(failed.payment.result, SimulatedPayment.Result.FAILURE)
        self.assertEqual(SecurityEvent.objects.filter(kind='PAYMENT_FAILED').count(), 1)

    def test_owner_isolation_and_operator_read_only(self):
        order = self.create_order()
        self.client.force_login(self.other)
        self.assertNotContains(self.client.get(reverse('orders:list')), f'Orden {order.pk}')
        self.assertEqual(self.client.get(reverse('orders:detail', args=[order.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('orders:pay', args=[order.pk]), {'result': 'SUCCESS'}).status_code, 404)
        self.client.force_login(self.operator)
        self.assertContains(self.client.get(reverse('orders:list')), f'Orden {order.pk}')
        self.assertEqual(self.client.get(reverse('orders:detail', args=[order.pk])).status_code, 200)
        self.assertEqual(self.client.post(reverse('orders:pay', args=[order.pk]), {'result': 'SUCCESS'}).status_code, 403)
        self.assertEqual(self.client.post(reverse('cart:add', args=[self.product.pk])).status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('orders:list')).status_code, 403)
        self.assertTrue(SecurityEvent.objects.filter(kind='ORDER_ACCESS_DENIED').exists())
        self.assertEqual(SimulatedPayment.objects.count(), 0)

    def test_existing_inconsistent_payment_is_never_accepted_or_overwritten(self):
        order = self.create_order()
        SimulatedPayment.objects.create(order=order, result=SimulatedPayment.Result.FAILURE)
        url = reverse('orders:pay', args=[order.pk])
        self.assertEqual(self.client.post(url, {'result': 'SUCCESS'}).status_code, 409)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertEqual(order.payment.result, SimulatedPayment.Result.FAILURE)
        Order.objects.filter(pk=order.pk).update(status=Order.Status.PAID)
        self.assertEqual(self.client.post(url, {'result': 'FAILURE'}).status_code, 409)
        self.assertEqual(SimulatedPayment.objects.filter(order=order).count(), 1)

    def test_csrf_is_required_and_valid_tokens_work(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        add_url = reverse('cart:add', args=[self.product.pk])
        self.assertEqual(client.post(add_url).status_code, 403)
        client.get(reverse('catalog:detail', args=[self.product.pk]))
        token = client.cookies['csrftoken'].value
        self.assertEqual(client.post(add_url, {'csrfmiddlewaretoken': token}).status_code, 302)
        cart_page = client.get(reverse('cart:detail'))
        data = {'key': str(cart_page.context['cart'].checkout_key), 'quote': cart_page.context['quote']}
        self.assertEqual(client.post(reverse('orders:checkout'), data).status_code, 403)
        data['csrfmiddlewaretoken'] = token
        self.assertEqual(client.post(reverse('orders:checkout'), data).status_code, 302)
        order = Order.objects.get()
        self.assertEqual(client.post(reverse('orders:pay', args=[order.pk]), {'result': 'SUCCESS'}).status_code, 403)
        self.assertEqual(client.post(reverse('orders:pay', args=[order.pk]), {
            'result': 'SUCCESS', 'csrfmiddlewaretoken': token,
        }).status_code, 302)

    def test_database_failures_roll_back_checkout_and_payment(self):
        self.add()
        data = self.quote()
        cart_key = data['key']
        with patch('orders.services.OrderItem.objects.bulk_create', side_effect=IntegrityError('error de prueba')):
            with self.assertRaises(IntegrityError):
                checkout(self.user, self.user.cart.checkout_key, data['quote'])
        self.assertFalse(Order.objects.exists())
        self.assertEqual(CartItem.objects.count(), 1)
        self.assertEqual(str(Cart.objects.get(user=self.user).checkout_key), cart_key)
        self.assertFalse(SecurityEvent.objects.filter(kind='ORDER_CREATED').exists())
        order = checkout(self.user, self.user.cart.checkout_key, data['quote'])
        with patch('orders.services.SimulatedPayment.objects.create', side_effect=IntegrityError('error de prueba')):
            with self.assertRaises(IntegrityError):
                simulate_payment(order, SimulatedPayment.Result.SUCCESS)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertFalse(SimulatedPayment.objects.exists())
        self.assertFalse(SecurityEvent.objects.filter(kind='PAYMENT_SUCCEEDED').exists())


class ConcurrentPurchaseTests(ReceiptKeysMixin, TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='race', email='race@example.com', password='Password-482!')
        self.product = product()
        self.cart = get_cart(self.user)
        CartItem.objects.create(cart=self.cart, product=self.product)

    def run_parallel(self, action):
        barrier = threading.Barrier(2)
        def run(value):
            close_old_connections()
            try:
                barrier.wait(timeout=5)
                return action(value)
            except OperationalError as exc:
                code = getattr(exc.__cause__, 'sqlite_errorcode', 0) & 0xff
                if code not in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
                    raise
                return 'locked'
            except OrderConflict:
                return 'conflict'
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(run, (0, 1)))

    def test_concurrent_checkout_and_payment_do_not_duplicate(self):
        key = self.cart.checkout_key
        quote = sign_quote(self.cart, current_products(self.cart))
        self.run_parallel(lambda _: checkout(self.user, key, quote))
        order = checkout(self.user, key, quote)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(order.items.count(), 1)
        outcomes = [SimulatedPayment.Result.SUCCESS, SimulatedPayment.Result.FAILURE]
        self.run_parallel(lambda index: simulate_payment(order, outcomes[index]))
        order.refresh_from_db()
        if order.status == Order.Status.PENDING:
            simulate_payment(order, SimulatedPayment.Result.SUCCESS)
            order.refresh_from_db()
        payment = SimulatedPayment.objects.get(order=order)
        self.assertEqual(SimulatedPayment.objects.count(), 1)
        self.assertEqual(Receipt.objects.filter(payment=payment).count(), int(payment.result == 'SUCCESS'))
        self.assertEqual(
            order.status,
            Order.Status.PAID if payment.result == SimulatedPayment.Result.SUCCESS else Order.Status.FAILED,
        )
        simulate_payment(order, payment.result)
        with self.assertRaises(OrderConflict):
            simulate_payment(order, SimulatedPayment.Result.FAILURE if payment.result == 'SUCCESS' else 'SUCCESS')
