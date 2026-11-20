import hashlib
import random
import tempfile
from pathlib import Path
from unittest.mock import patch

import pymupdf
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .models import PrivateCatalogStorage, Product
from .validators import MAX_PDF_SIZE, inspect_pdf

User = get_user_model()


def pdf_bytes(text='Contenido'):
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((72, 72), text)
        return document.tobytes()


def upload(data=None, name='libro.pdf'):
    return SimpleUploadedFile(name, data if data is not None else pdf_bytes(), content_type='application/pdf')


@override_settings(ALLOWED_HOSTS=['testserver'])
class CatalogTests(TestCase):
    def setUp(self):
        private_dir = tempfile.TemporaryDirectory(prefix='catalog-private-test-')
        self.addCleanup(private_dir.cleanup)
        settings_override = override_settings(PRIVATE_CATALOG_ROOT=Path(private_dir.name))
        settings_override.enable()
        self.addCleanup(settings_override.disable)
        storage_patch = patch.object(Product._meta.get_field('pdf'), 'storage', PrivateCatalogStorage())
        storage_patch.start()
        self.addCleanup(storage_patch.stop)
        self.private_dir = Path(private_dir.name)
        self.operator = User.objects.create_user(
            username='operator', email='operator@example.com', password='Password-482!',
            role=User.Role.OPERADOR,
        )

    def create_product(self, status=Product.Status.PUBLISHED, name='Visible', data=None):
        return Product.objects.create(
            name=name, description='Descripción segura', price='12.50',
            status=status, pdf=upload(data),
        )

    def test_home_public_catalog_and_unpublished_detail(self):
        visible = self.create_product()
        draft = self.create_product(Product.Status.DRAFT, 'Borrador')
        archived = self.create_product(Product.Status.ARCHIVED, 'Archivado')
        self.assertEqual(self.client.get(reverse('catalog:home')).status_code, 200)
        response = self.client.get(reverse('catalog:list'))
        self.assertContains(response, visible.name)
        self.assertNotContains(response, draft.name)
        self.assertNotContains(response, archived.name)
        self.assertContains(self.client.get(reverse('catalog:detail', args=[visible.pk])), visible.name)
        for product in (draft, archived):
            self.assertEqual(self.client.get(reverse('catalog:detail', args=[product.pk])).status_code, 404)

    def test_only_active_operator_can_manage_even_when_not_staff(self):
        product = self.create_product(Product.Status.DRAFT)
        urls = [
            reverse('catalog:manage'), reverse('catalog:create'),
            reverse('catalog:edit', args=[product.pk]),
        ]
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 302)
        for role, superuser in ((User.Role.CLIENTE, False), (User.Role.ADMINISTRADOR, True)):
            user = User.objects.create_user(
                username=role, email=f'{role}@example.com', password='Password-482!',
                role=role, is_staff=superuser, is_superuser=superuser,
            )
            self.client.force_login(user)
            for url in urls:
                self.assertEqual(self.client.get(url).status_code, 403)
                self.assertEqual(self.client.post(url, {}).status_code, 403)
        self.assertFalse(self.operator.is_staff)
        self.client.force_login(self.operator)
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 200)
        self.operator.is_active = False
        self.operator.save()
        self.assertEqual(self.client.get(urls[0]).status_code, 302)

    def test_create_edit_and_private_storage_with_server_calculated_hash(self):
        self.client.force_login(self.operator)
        original = pdf_bytes('Original')
        response = self.client.post(reverse('catalog:create'), {
            'name': '<script>alert(1)</script>', 'description': 'Primero',
            'price': '12.50', 'status': Product.Status.PUBLISHED,
            'pdf': upload(original, '../../nombre.pdf'), 'sha256': 'forged',
        })
        self.assertRedirects(response, reverse('catalog:manage'))
        product = Product.objects.get()
        self.assertEqual(product.sha256, hashlib.sha256(original).hexdigest())
        self.assertRegex(product.pdf.name, r'^[0-9a-f]{32}\.pdf$')
        self.assertEqual(Path(product.pdf.path).parent, self.private_dir)
        self.assertEqual(Path(product.pdf.path).read_bytes(), original)
        with self.assertRaises(ValueError):
            product.pdf.url
        response = self.client.get(reverse('catalog:detail', args=[product.pk]))
        self.assertNotContains(response, '<script>alert(1)</script>')
        self.assertContains(response, '&lt;script&gt;')
        self.assertNotContains(response, product.pdf.name)
        self.assertNotContains(response, product.sha256)
        self.assertEqual(self.client.get('/media/' + product.pdf.name).status_code, 404)

        updated = pdf_bytes('Actualizado')
        response = self.client.post(reverse('catalog:edit', args=[product.pk]), {
            'name': 'Editado', 'description': 'Segundo', 'price': '5.00',
            'status': Product.Status.ARCHIVED, 'pdf': upload(updated),
        })
        self.assertRedirects(response, reverse('catalog:manage'))
        product.refresh_from_db()
        self.assertEqual(product.sha256, hashlib.sha256(updated).hexdigest())
        self.assertEqual(Path(product.pdf.path).read_bytes(), updated)
        self.assertEqual(self.client.get(reverse('catalog:detail', args=[product.pk])).status_code, 404)
        response = self.client.post(reverse('catalog:edit', args=[product.pk]), {
            'name': 'Editado', 'description': 'Segundo', 'price': '5.00',
            'status': Product.Status.DRAFT,
        })
        self.assertEqual(response.status_code, 302)
        product.refresh_from_db()
        self.assertEqual(product.sha256, hashlib.sha256(updated).hexdigest())

    def test_invalid_uploads_are_rejected_without_writing_files(self):
        with pymupdf.open() as document:
            document.new_page()
            encrypted = document.tobytes(
                encryption=pymupdf.PDF_ENCRYPT_AES_256,
                owner_pw='owner-password', user_pw='user-password',
            )
            encrypted_empty_password = document.tobytes(
                encryption=pymupdf.PDF_ENCRYPT_AES_256,
                owner_pw='owner-password', user_pw='',
            )
        cases = [
            ('file.txt', pdf_bytes()),
            ('file.pdf', b'not a PDF'),
            ('file.pdf', b'%PDF-1.7\nbroken'),
            ('file.pdf', encrypted),
            ('file.pdf', encrypted_empty_password),
            ('file.pdf', b'%PDF-' + b'x' * MAX_PDF_SIZE),
        ]
        self.client.force_login(self.operator)
        for filename, data in cases:
            with self.subTest(filename=filename, length=len(data)):
                response = self.client.post(reverse('catalog:create'), {
                    'name': 'Rechazado', 'description': 'Descripción',
                    'price': '1.00', 'status': Product.Status.PUBLISHED,
                    'pdf': upload(data, filename),
                })
                self.assertEqual(response.status_code, 200)
                self.assertIn('pdf', response.context['form'].errors)
        self.assertFalse(Product.objects.exists())
        self.assertEqual(list(self.private_dir.iterdir()), [])
        with self.assertRaises(ValidationError):
            self.create_product(data=b'%PDF-not-valid')

    def test_exact_maximum_file_size_is_accepted(self):
        payload = random.Random(1).randbytes(MAX_PDF_SIZE - 1100)
        with pymupdf.open() as document:
            document.new_page()
            document.embfile_add('data.bin', payload)
            data = document.tobytes()
        padding = MAX_PDF_SIZE - len(data)
        self.assertTrue(0 <= padding <= 512)
        data += b' ' * padding
        self.assertEqual(inspect_pdf(upload(data)), hashlib.sha256(data).hexdigest())

    def test_price_status_and_required_fields_are_validated(self):
        self.client.force_login(self.operator)
        response = self.client.post(reverse('catalog:create'), {
            'name': '', 'description': 'Descripción', 'price': '-1',
            'status': 'INVALID', 'pdf': upload(),
        })
        for field in ('name', 'price', 'status'):
            self.assertIn(field, response.context['form'].errors)
        self.assertFalse(Product.objects.exists())
        with self.assertRaises(IntegrityError), transaction.atomic():
            Product.objects.create(
                name='Inválido', description='Descripción', price=-1,
                status=Product.Status.DRAFT, pdf=upload(),
            )

    def test_csrf_required_for_create_and_edit(self):
        product = self.create_product(Product.Status.DRAFT)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.operator)
        self.assertEqual(client.post(reverse('catalog:create'), {}).status_code, 403)
        edit_url = reverse('catalog:edit', args=[product.pk])
        self.assertEqual(client.post(edit_url, {}).status_code, 403)
        client.get(edit_url)
        response = client.post(edit_url, {
            'name': 'Actualizado', 'description': 'Descripción', 'price': '1.00',
            'status': Product.Status.PUBLISHED,
            'csrfmiddlewaretoken': client.cookies['csrftoken'].value,
        })
        self.assertEqual(response.status_code, 302)
        product.refresh_from_db()
        self.assertEqual(product.status, Product.Status.PUBLISHED)
