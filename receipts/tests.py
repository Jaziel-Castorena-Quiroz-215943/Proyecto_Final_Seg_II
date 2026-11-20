import base64
import hashlib
import json
import tempfile
import uuid
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.models import SecurityEvent
from catalog.models import Product
from orders.models import Order, OrderItem, SimulatedPayment
from orders.services import simulate_payment

from .crypto import InvalidReceipt, canonical_json, verify_envelope
from .models import Receipt
from .services import receipt_envelope, verify_stored_receipt
from .test_helpers import ReceiptKeysMixin

User = get_user_model()


@override_settings(ALLOWED_HOSTS=['testserver'])
class ReceiptTests(ReceiptKeysMixin, TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='cliente', email='cliente@example.com', password='Password-482!')
        self.other = User.objects.create_user(username='otro', email='otro@example.com', password='Password-482!')
        self.operator = User.objects.create_user(
            username='operador', email='operador@example.com', password='Password-482!', role=User.Role.OPERADOR,
        )
        self.product = Product(
            name='Libro', description='PDF', price='12.50', status=Product.Status.PUBLISHED,
            pdf='fixture.pdf', sha256='a' * 64,
        )
        Product.objects.bulk_create([self.product])
        self.order = Order.objects.create(user=self.user, checkout_key=uuid.uuid4(), total=Decimal('12.50'))
        OrderItem.objects.create(order=self.order, product=self.product, product_name='Libro', unit_price='12.50')
        self.client.force_login(self.user)

    def pay(self, result='SUCCESS'):
        return self.client.post(reverse('orders:pay', args=[self.order.pk]), {'result': result})

    def receipt(self):
        self.assertEqual(self.pay().status_code, 302)
        return Receipt.objects.get(payment__order=self.order)

    def test_receipt_is_signed_with_real_asymmetric_key_and_idempotent(self):
        receipt = self.receipt()
        envelope = verify_stored_receipt(receipt)
        data = canonical_json(envelope['body']).encode('utf-8')
        self.assertEqual(hashlib.sha256(data).hexdigest(), envelope['sha256'])
        public = serialization.load_pem_public_key(
            (Path(settings.RECEIPTS_PUBLIC_KEYS_DIR) / 'test-key.pem').read_bytes(),
        )
        public.verify(
            base64.b64decode(envelope['signature']), data,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
            hashes.SHA256(),
        )
        self.assertEqual(envelope['body']['total'], '12.50')
        self.assertEqual(envelope['body']['items'][0]['name'], 'Libro')
        self.assertEqual(envelope['body']['payment_type'], 'SIMULATED')
        self.assertEqual(self.pay().status_code, 302)
        self.assertEqual(Receipt.objects.count(), 1)
        receipt.refresh_from_db()
        self.assertEqual(receipt.signature, envelope['signature'])
        self.assertEqual(SecurityEvent.objects.filter(kind='RECEIPT_ISSUED').count(), 1)

    def test_tampering_and_untrusted_keys_fail(self):
        receipt = self.receipt()
        original = receipt_envelope(receipt)
        tampered = json.loads(json.dumps(original))
        tampered['body']['total'] = '0.01'
        tampered['sha256'] = hashlib.sha256(canonical_json(tampered['body']).encode('utf-8')).hexdigest()
        with self.assertRaises(InvalidReceipt):
            verify_envelope(tampered)
        altered_signature = dict(original, signature=base64.b64encode(b'wrong').decode('ascii'))
        with self.assertRaises(InvalidReceipt):
            verify_envelope(altered_signature)
        wrong_key = json.loads(json.dumps(original))
        wrong_key['body']['key_id'] = '../test-key'
        wrong_key['sha256'] = hashlib.sha256(canonical_json(wrong_key['body']).encode('utf-8')).hexdigest()
        with self.assertRaises(InvalidReceipt):
            verify_envelope(wrong_key)
        Receipt.objects.filter(pk=receipt.pk).update(sha256='0' * 64)
        self.assertEqual(self.client.get(reverse('receipts:detail', args=[receipt.pk])).status_code, 400)
        self.assertTrue(SecurityEvent.objects.filter(kind='RECEIPT_INVALID', user=self.user).exists())

    def test_access_and_verification_with_csrf(self):
        receipt = self.receipt()
        document_url = reverse('receipts:document', args=[receipt.pk])
        response = self.client.get(document_url)
        self.assertEqual(response.status_code, 200)
        envelope = response.json()
        self.assertEqual(self.client.post(reverse('receipts:verify'), {'document': json.dumps(envelope)}).status_code, 200)
        self.assertTrue(SecurityEvent.objects.filter(kind='RECEIPT_VERIFIED', user=self.user).exists())
        envelope['body']['total'] = '0.01'
        self.assertEqual(self.client.post(reverse('receipts:verify'), {'document': json.dumps(envelope)}).status_code, 400)
        self.assertEqual(self.client.post(reverse('receipts:verify'), {'document': '{"body":1,"body":2}'}).status_code, 400)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(document_url).status_code, 404)
        self.assertEqual(self.client.get(reverse('receipts:detail', args=[receipt.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('receipts:verify'), {
            'document': json.dumps(receipt_envelope(receipt)),
        }).status_code, 404)
        self.client.force_login(self.operator)
        self.assertEqual(self.client.get(document_url).status_code, 200)
        admin = User.objects.create_superuser('admin', 'admin@example.com', 'Password-482!')
        self.client.force_login(admin)
        self.assertEqual(self.client.get(document_url).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(document_url).status_code, 302)
        csrf = Client(enforce_csrf_checks=True)
        csrf.force_login(self.user)
        self.assertEqual(csrf.post(reverse('receipts:verify'), {'document': json.dumps(envelope)}).status_code, 403)
        csrf.get(reverse('receipts:verify'))
        self.assertEqual(csrf.post(reverse('receipts:verify'), {
            'document': json.dumps(receipt_envelope(receipt)),
            'csrfmiddlewaretoken': csrf.cookies['csrftoken'].value,
        }).status_code, 200)

    def test_failed_or_unconfigured_payment_does_not_issue_receipt(self):
        with override_settings(RECEIPTS_PRIVATE_KEY_PATH=None):
            with self.assertLogs('orders.views', level='ERROR'):
                self.assertEqual(self.pay().status_code, 503)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PENDING)
        self.assertFalse(SimulatedPayment.objects.exists())
        self.assertFalse(Receipt.objects.exists())
        self.assertTrue(SecurityEvent.objects.filter(kind='RECEIPT_ERROR').exists())
        with override_settings(RECEIPTS_PRIVATE_KEY_PATH=None):
            self.assertEqual(self.pay('FAILURE').status_code, 302)
        self.assertFalse(Receipt.objects.exists())

    def test_key_mismatch_and_order_inconsistency_fail_closed(self):
        other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        with patch('receipts.crypto.public_key', return_value=other_key.public_key()):
            with self.assertLogs('orders.views', level='ERROR'):
                self.assertEqual(self.pay().status_code, 503)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PENDING)
        Order.objects.filter(pk=self.order.pk).update(total='99.00')
        with self.assertLogs('orders.views', level='ERROR'):
            self.assertEqual(self.pay().status_code, 503)
        self.assertFalse(Receipt.objects.exists())
        self.assertFalse(SimulatedPayment.objects.exists())

    def test_changed_order_or_payment_invalidates_stored_receipt(self):
        receipt = self.receipt()
        OrderItem.objects.filter(order=self.order).update(unit_price='0.01')
        with self.assertRaises(InvalidReceipt):
            verify_stored_receipt(receipt)
        self.assertEqual(self.client.get(reverse('receipts:document', args=[receipt.pk])).status_code, 400)

    def test_receipt_write_failure_rolls_back_payment(self):
        with patch('receipts.services.Receipt.objects.create', side_effect=IntegrityError('error de prueba')):
            with self.assertRaises(IntegrityError):
                simulate_payment(self.order, SimulatedPayment.Result.SUCCESS)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PENDING)
        self.assertFalse(SimulatedPayment.objects.exists())
        self.assertFalse(SecurityEvent.objects.filter(kind='PAYMENT_SUCCEEDED').exists())
        self.assertFalse(SecurityEvent.objects.filter(kind='RECEIPT_ISSUED').exists())

    def test_rotation_retains_old_public_key_and_missing_key_is_explicit(self):
        old = self.receipt()
        root = Path(settings.RECEIPTS_PRIVATE_KEY_PATH).parent
        private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        private_path = root / 'rotated.pem'
        private_path.write_bytes(private.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption(),
        ))
        public_path = Path(settings.RECEIPTS_PUBLIC_KEYS_DIR) / 'rotated.pem'
        public_path.write_bytes(private.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
        ))
        second = Order.objects.create(user=self.user, checkout_key=uuid.uuid4(), total=Decimal('12.50'))
        OrderItem.objects.create(order=second, product=self.product, product_name='Libro', unit_price='12.50')
        with override_settings(
            RECEIPTS_PRIVATE_KEY_PATH=str(private_path), RECEIPTS_PRIVATE_KEY_PASSWORD=None, RECEIPTS_KEY_ID='rotated',
        ):
            simulate_payment(second, SimulatedPayment.Result.SUCCESS)
            self.assertEqual(verify_stored_receipt(old)['body']['key_id'], 'test-key')
            self.assertEqual(verify_stored_receipt(second.payment.receipt)['body']['key_id'], 'rotated')
        with tempfile.TemporaryDirectory(prefix='receipt-missing-key-') as empty_dir:
            with override_settings(RECEIPTS_PUBLIC_KEYS_DIR=empty_dir):
                with self.assertLogs('receipts.views', level='ERROR'):
                    self.assertEqual(self.client.get(reverse('receipts:detail', args=[old.pk])).status_code, 503)

    def test_historical_success_is_not_reissued_on_retry(self):
        Order.objects.filter(pk=self.order.pk).update(status=Order.Status.PAID)
        SimulatedPayment.objects.create(order=self.order, result=SimulatedPayment.Result.SUCCESS)
        self.assertEqual(self.pay().status_code, 302)
        self.assertFalse(Receipt.objects.exists())
