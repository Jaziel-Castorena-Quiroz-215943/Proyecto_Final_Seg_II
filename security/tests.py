import hashlib
import tempfile
from pathlib import Path
from unittest.mock import patch

import pymupdf
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.models import SecurityEvent, User
from cart.models import CartItem
from cart.services import current_products, get_cart, sign_quote
from catalog.models import PrivateCatalogStorage, Product
from orders.models import Order, OrderItem, SimulatedPayment
from orders.services import checkout, simulate_payment
from receipts.services import verify_stored_receipt
from receipts.test_helpers import ReceiptKeysMixin

from .fingerprinting import (
    MAX_MARKED_PDF_SIZE, FingerprintError, extract_token, identify_download, issue_download, watermark_pdf,
)
from .models import DownloadFingerprint

UserModel = get_user_model()


def original_pdf(text='Original'):
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((72, 72), text)
        rotated = document.new_page()
        rotated.insert_text((72, 72), 'Pagina girada')
        rotated.set_rotation(90)
        return document.tobytes()


@override_settings(ALLOWED_HOSTS=['testserver'])
class FingerprintTests(ReceiptKeysMixin, TestCase):
    def setUp(self):
        private_dir = tempfile.TemporaryDirectory(prefix='fingerprint-private-test-')
        self.addCleanup(private_dir.cleanup)
        settings_override = override_settings(PRIVATE_CATALOG_ROOT=Path(private_dir.name))
        settings_override.enable()
        self.addCleanup(settings_override.disable)
        storage_patch = patch.object(Product._meta.get_field('pdf'), 'storage', PrivateCatalogStorage())
        storage_patch.start()
        self.addCleanup(storage_patch.stop)
        self.user = UserModel.objects.create_user(username='cliente', email='cliente@example.com', password='Password-482!')
        self.other = UserModel.objects.create_user(username='otro', email='otro@example.com', password='Password-482!')
        self.operator = UserModel.objects.create_user(
            username='operador', email='operador@example.com', password='Password-482!', role=User.Role.OPERADOR,
        )
        self.admin = UserModel.objects.create_superuser('admin', 'admin@example.com', 'Password-482!')
        self.source = original_pdf()
        self.product = Product.objects.create(
            name='Libro', description='PDF', price='12.50', status=Product.Status.PUBLISHED,
            pdf=SimpleUploadedFile('book.pdf', self.source, content_type='application/pdf'),
        )
        cart = get_cart(self.user)
        CartItem.objects.create(cart=cart, product=self.product)
        self.order = checkout(self.user, cart.checkout_key, sign_quote(cart, current_products(cart)))
        self.item = self.order.items.get()
        self.client.force_login(self.user)

    def pay(self):
        simulate_payment(self.order, SimulatedPayment.Result.SUCCESS)
        self.order.refresh_from_db()

    def download(self):
        return self.client.post(reverse('security:download', args=[self.item.pk]))

    def test_paid_downloads_are_unique_traceable_and_preserve_original_and_receipt(self):
        self.pay()
        receipt = self.order.payment.receipt
        signature = receipt.signature
        first = self.download()
        second = self.download()
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first['Content-Type'], 'application/pdf')
        self.assertIn('attachment', first['Content-Disposition'])
        self.assertIn('no-store', first['Cache-Control'])
        self.assertNotEqual(first.content, second.content)
        tokens = [extract_token(first.content), extract_token(second.content)]
        self.assertNotEqual(tokens[0], tokens[1])
        self.assertEqual(DownloadFingerprint.objects.count(), 2)
        self.assertEqual(identify_download(first.content).user_id, self.user.pk)
        self.assertEqual(identify_download(first.content).order_item_id, self.item.pk)
        with pymupdf.open(stream=first.content, filetype='pdf') as document:
            self.assertEqual(document.page_count, 2)
            for page in document:
                text = page.get_text()
                self.assertIn('FPR-' + tokens[0], text)
                self.assertNotIn(self.user.username, text)
                self.assertNotIn(self.user.email, text)
        self.assertEqual(Path(self.product.pdf.path).read_bytes(), self.source)
        self.assertEqual(hashlib.sha256(self.source).hexdigest(), self.item.pdf_sha256)
        receipt.refresh_from_db()
        self.assertEqual(receipt.signature, signature)
        verify_stored_receipt(receipt)
        self.assertEqual(SecurityEvent.objects.filter(kind='DOWNLOAD_CREATED', user=self.user).count(), 2)

    def test_original_version_is_preserved_when_catalog_product_changes(self):
        self.pay()
        original_name = self.item.pdf_name
        self.product.pdf = SimpleUploadedFile('new.pdf', original_pdf('Replacement'))
        self.product.status = Product.Status.ARCHIVED
        self.product.save()
        self.assertNotEqual(self.product.pdf.name, original_name)
        response = self.download()
        self.assertEqual(response.status_code, 200)
        with pymupdf.open(stream=response.content, filetype='pdf') as document:
            self.assertIn('Original', document[0].get_text())
            self.assertNotIn('Replacement', document[0].get_text())

    def test_download_requires_owner_approved_payment_and_client_role(self):
        self.assertEqual(self.download().status_code, 404)
        Order.objects.filter(pk=self.order.pk).update(status=Order.Status.PAID)
        self.assertEqual(self.download().status_code, 404)
        SimulatedPayment.objects.create(order=self.order, result=SimulatedPayment.Result.FAILURE)
        self.assertEqual(self.download().status_code, 404)
        SimulatedPayment.objects.filter(order=self.order).delete()
        Order.objects.filter(pk=self.order.pk).update(status=Order.Status.PENDING)
        self.pay()
        self.client.force_login(self.other)
        self.assertEqual(self.download().status_code, 404)
        self.client.force_login(self.operator)
        self.assertEqual(self.download().status_code, 403)
        self.client.logout()
        self.assertEqual(self.download().status_code, 302)
        self.assertFalse(DownloadFingerprint.objects.exists())
        self.assertTrue(SecurityEvent.objects.filter(kind='DOWNLOAD_DENIED').exists())

    def test_legacy_or_altered_original_is_rejected(self):
        self.pay()
        OrderItem.objects.filter(pk=self.item.pk).update(pdf_name=None, pdf_sha256=None)
        self.assertContains(self.client.get(reverse('orders:detail', args=[self.order.pk])), 'no tiene una versión')
        self.assertEqual(self.download().status_code, 409)
        OrderItem.objects.filter(pk=self.item.pk).update(pdf_name=self.product.pdf.name, pdf_sha256=self.product.sha256)
        Path(self.product.pdf.path).write_bytes(b'tampered')
        self.assertEqual(self.download().status_code, 409)
        self.assertFalse(DownloadFingerprint.objects.exists())
        self.assertEqual(SecurityEvent.objects.filter(kind='DOWNLOAD_ERROR', user=self.user).count(), 2)

    def test_superuser_can_extract_only_an_unmodified_issued_pdf(self):
        self.pay()
        data = self.download().content
        url = reverse('security:extract')
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.operator)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.admin)
        response = self.client.post(url, {'pdf': SimpleUploadedFile('evidence.pdf', data)})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.user.username)
        self.assertContains(response, self.item.product_name)
        self.assertTrue(SecurityEvent.objects.filter(kind='FINGERPRINT_EXTRACTED', user=self.admin).exists())
        response = self.client.post(url, {'pdf': SimpleUploadedFile('changed.pdf', data + b'\n')})
        self.assertEqual(response.status_code, 400)
        self.assertTrue(SecurityEvent.objects.filter(kind='FINGERPRINT_INVALID', user=self.admin).exists())
        with self.assertRaises(FingerprintError):
            identify_download(self.source)
        counterfeit = watermark_pdf(original_pdf('Otro archivo'), extract_token(data))
        with self.assertRaises(FingerprintError):
            identify_download(counterfeit)

    def test_csrf_required_for_download_and_extraction(self):
        self.pay()
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        url = reverse('security:download', args=[self.item.pk])
        self.assertEqual(client.post(url).status_code, 403)
        client.get(reverse('orders:detail', args=[self.order.pk]))
        response = client.post(url, {'csrfmiddlewaretoken': client.cookies['csrftoken'].value})
        self.assertEqual(response.status_code, 200)
        client.force_login(self.admin)
        extract_url = reverse('security:extract')
        self.assertEqual(client.post(extract_url, {'pdf': SimpleUploadedFile('a.pdf', response.content)}).status_code, 403)
        client.get(extract_url)
        result = client.post(extract_url, {
            'pdf': SimpleUploadedFile('a.pdf', response.content),
            'csrfmiddlewaretoken': client.cookies['csrftoken'].value,
        })
        self.assertEqual(result.status_code, 200)

    def test_documents_with_signature_fields_are_not_modified(self):
        with pymupdf.open() as document:
            page = document.new_page()
            widget = pymupdf.Widget()
            widget.field_name = 'Signature1'
            widget.field_type = pymupdf.PDF_WIDGET_TYPE_SIGNATURE
            widget.rect = pymupdf.Rect(10, 10, 100, 50)
            page.add_widget(widget)
            signed_form = document.tobytes()
        with self.assertRaises(FingerprintError):
            watermark_pdf(signed_form, 'a' * 32)

    def test_small_page_keeps_visible_and_recoverable_marker(self):
        with pymupdf.open() as document:
            document.new_page(width=40, height=40)
            source = document.tobytes()
        token = 'b' * 32
        marked = watermark_pdf(source, token)
        self.assertEqual(extract_token(marked), token)
        with pymupdf.open(stream=marked, filetype='pdf') as document:
            self.assertIn('FPR-' + token, document[0].get_text())

    def test_reserved_marker_in_original_is_not_overwritten(self):
        with pymupdf.open(stream=self.source, filetype='pdf') as document:
            document.embfile_add('__platform_fingerprint_v1__', b'a' * 32)
            source = document.tobytes()
        with self.assertRaises(FingerprintError):
            watermark_pdf(source, 'b' * 32)

    def test_extraction_rejects_files_over_size_limit(self):
        with self.assertRaises(FingerprintError):
            extract_token(b'%PDF-' + b'x' * MAX_MARKED_PDF_SIZE)

    def test_audit_failure_rolls_back_issued_fingerprint(self):
        self.pay()
        with patch('security.fingerprinting.SecurityEvent.objects.create', side_effect=IntegrityError('error de prueba')):
            with self.assertRaises(IntegrityError):
                issue_download(self.user, self.item.pk)
        self.assertFalse(DownloadFingerprint.objects.exists())
