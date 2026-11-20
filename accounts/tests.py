import re
from datetime import datetime, timedelta
from urllib.parse import urlsplit
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import identify_hasher
from django.contrib.auth.models import Permission
from django.contrib.auth.tokens import default_token_generator
from django.contrib.contenttypes.models import ContentType
from django.core import mail
from django.db import IntegrityError, transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .models import SecurityEvent

User = get_user_model()
PASSWORD = 'A-long-and-unique-password-482!'


@override_settings(ALLOWED_HOSTS=['testserver'], MAILERS={
    'default': {'BACKEND': 'django.core.mail.backends.locmem.EmailBackend'},
})
class AccountTests(TestCase):
    def create_user(self, username='alice', email='alice@example.com'):
        return User.objects.create_user(username=username, email=email, password=PASSWORD)

    def test_registration_enforces_validation_and_ignores_privilege_fields(self):
        response = self.client.post(reverse('accounts:register'), {
            'username': 'alice', 'email': 'Alice@Example.com',
            'password1': PASSWORD, 'password2': PASSWORD,
            'role': User.Role.ADMINISTRADOR, 'is_staff': 'on', 'is_superuser': 'on',
        })
        self.assertRedirects(response, reverse('accounts:login'))
        user = User.objects.get(username='alice')
        self.assertEqual(user.email, 'alice@example.com')
        self.assertEqual(user.role, User.Role.CLIENTE)
        self.assertFalse(user.is_staff or user.is_superuser)
        self.assertEqual(identify_hasher(user.password).algorithm, 'argon2')
        self.assertTrue(user.password.startswith('argon2$argon2id$'))
        self.assertTrue(SecurityEvent.objects.filter(kind='REGISTER', user=user).exists())
        response = self.client.post(reverse('accounts:register'), {
            'username': 'bob', 'email': 'ALICE@example.com',
            'password1': '123', 'password2': '123',
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('email', response.context['form'].errors)
        self.assertIn('password2', response.context['form'].errors)
        self.assertFalse(User.objects.filter(username='bob').exists())

    def test_email_uniqueness_is_enforced_by_database(self):
        self.create_user()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.create_user('bob', 'ALICE@example.com')

    def test_login_logout_profile_and_security_events(self):
        user = self.create_user()
        self.assertEqual(self.client.get(reverse('accounts:profile')).status_code, 302)
        self.client.post(reverse('accounts:login'), {'username': 'alice', 'password': 'wrong'})
        self.assertTrue(SecurityEvent.objects.filter(kind='LOGIN_FAILED', user__isnull=True).exists())
        response = self.client.post(reverse('accounts:login'), {'username': 'alice', 'password': PASSWORD})
        self.assertRedirects(response, reverse('accounts:profile'))
        self.assertTrue(SecurityEvent.objects.filter(kind='LOGIN', user=user).exists())
        response = self.client.post(reverse('accounts:profile'), {
            'first_name': 'Alice', 'last_name': 'Example', 'email': 'NEW@example.com',
            'role': User.Role.ADMINISTRADOR, 'is_staff': 'on',
        })
        self.assertRedirects(response, reverse('accounts:profile'))
        user.refresh_from_db()
        self.assertEqual(user.email, 'new@example.com')
        self.assertEqual(user.role, User.Role.CLIENTE)
        self.assertFalse(user.is_staff)
        self.assertTrue(SecurityEvent.objects.filter(kind='PROFILE_UPDATED', user=user).exists())
        self.assertEqual(self.client.get(reverse('accounts:logout')).status_code, 405)
        self.client.post(reverse('accounts:logout'))
        self.assertTrue(SecurityEvent.objects.filter(kind='LOGOUT', user=user).exists())
        self.assertEqual(self.client.get(reverse('accounts:profile')).status_code, 302)

    def test_csrf_required_for_state_changing_endpoints(self):
        self.create_user()
        client = Client(enforce_csrf_checks=True)
        for name in ('register', 'login', 'password_reset', 'logout'):
            self.assertEqual(client.post(reverse('accounts:' + name), {}).status_code, 403, name)
        client.force_login(User.objects.get(username='alice'))
        self.assertEqual(client.post(reverse('accounts:profile'), {}).status_code, 403)
        client.get(reverse('accounts:profile'))
        response = client.post(reverse('accounts:profile'), {
            'first_name': 'Alice', 'last_name': 'Example', 'email': 'alice@example.com',
            'csrfmiddlewaretoken': client.cookies['csrftoken'].value,
        })
        self.assertEqual(response.status_code, 302)

    def test_password_reset_flow_and_one_time_token(self):
        user = self.create_user()
        url = reverse('accounts:password_reset')
        known = self.client.post(url, {'email': user.email})
        unknown = self.client.post(url, {'email': 'unknown@example.com'})
        self.assertEqual(known.url, unknown.url)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(SecurityEvent.objects.filter(kind='PASSWORD_RESET_REQUEST').count(), 2)
        reset_url = re.search(r'https?://\S+', mail.outbox[0].body).group()
        path = urlsplit(reset_url).path
        response = self.client.get(path)
        self.assertEqual(response.status_code, 302)
        confirm_path = response.url
        self.assertContains(self.client.get(confirm_path), 'Restablecer contraseña')
        response = self.client.post(confirm_path, {
            'new_password1': '123', 'new_password2': '123',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(SecurityEvent.objects.filter(kind='PASSWORD_RESET_COMPLETE').exists())
        response = self.client.post(confirm_path, {
            'new_password1': 'Another-unique-password-593!',
            'new_password2': 'Another-unique-password-593!',
        })
        self.assertRedirects(response, reverse('accounts:password_reset_complete'))
        user.refresh_from_db()
        self.assertTrue(user.check_password('Another-unique-password-593!'))
        self.assertTrue(SecurityEvent.objects.filter(kind='PASSWORD_RESET_COMPLETE', user=user).exists())
        self.assertContains(self.client.get(path), 'no es válido')

    def test_privileged_admin_and_audit_are_superuser_only(self):
        user = self.create_user()
        user.is_staff = True
        user.role = User.Role.ADMINISTRADOR
        user.save()
        for model, codename in ((User, 'change_user'), (SecurityEvent, 'view_securityevent')):
            content_type, _ = ContentType.objects.get_or_create(
                app_label='accounts', model=model._meta.model_name,
            )
            permission, _ = Permission.objects.get_or_create(
                content_type=content_type, codename=codename, defaults={'name': codename},
            )
            user.user_permissions.add(permission)
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse('admin:accounts_user_changelist')).status_code, 403)
        self.assertEqual(self.client.get(reverse('admin:accounts_securityevent_changelist')).status_code, 403)
        superuser = User.objects.create_superuser('root', 'root@example.com', PASSWORD)
        self.assertEqual(superuser.role, User.Role.ADMINISTRADOR)
        self.client.force_login(superuser)
        self.assertEqual(self.client.get(reverse('admin:accounts_securityevent_changelist')).status_code, 200)
        model_admin = admin.site._registry[SecurityEvent]
        request = type('Request', (), {'user': superuser})()
        self.assertFalse(model_admin.has_add_permission(request))
        self.assertFalse(model_admin.has_change_permission(request))
        self.assertFalse(model_admin.has_delete_permission(request))

    def test_password_reset_token_expires_after_one_hour(self):
        user = self.create_user()
        now = datetime.now()
        with patch.object(default_token_generator, '_now', return_value=now):
            token = default_token_generator.make_token(user)
        with patch.object(default_token_generator, '_now', return_value=now + timedelta(seconds=3601)):
            self.assertFalse(default_token_generator.check_token(user, token))

    def test_superuser_can_create_operator_in_admin(self):
        superuser = User.objects.create_superuser('root', 'root@example.com', PASSWORD)
        self.client.force_login(superuser)
        response = self.client.post(reverse('admin:accounts_user_add'), {
            'username': 'operator', 'email': 'operator@example.com',
            'password1': PASSWORD, 'password2': PASSWORD, 'role': User.Role.OPERADOR,
        })
        self.assertEqual(response.status_code, 302)
        operator = User.objects.get(username='operator')
        self.assertEqual(operator.role, User.Role.OPERADOR)
        self.assertFalse(operator.is_staff or operator.is_superuser)
