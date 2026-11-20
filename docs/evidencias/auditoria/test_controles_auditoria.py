import secrets

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, TestCase, override_settings
from django.urls import reverse


@override_settings(
    DEBUG=False,
    ALLOWED_HOSTS=['localhost'],
    SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO', 'https'),
    SECURE_SSL_REDIRECT=True,
    SESSION_COOKIE_SECURE=True,
    CSRF_COOKIE_SECURE=True,
    CSRF_TRUSTED_ORIGINS=['https://localhost:8443'],
)
class AuditControlTests(TestCase):
    headers = {'HTTP_HOST': 'localhost:8443', 'HTTP_X_FORWARDED_PROTO': 'https'}

    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.password = secrets.token_urlsafe(32)
        cls.users = {}
        for role in user_model.Role.values:
            cls.users[role] = user_model.objects.create_user(
                username='audit-' + role.lower(),
                email='audit-' + role.lower() + '@example.invalid',
                password=cls.password,
                role=role,
            )
        cls.superuser = user_model.objects.create_superuser(
            username='audit-superuser', email='audit-superuser@example.invalid',
            password=cls.password,
        )

    def test_anonymous_management_pages_require_authentication(self):
        self.assertIn('mode=memory', str(connection.settings_dict['NAME']))
        for name in (
            'admin:index', 'admin:accounts_user_changelist',
            'catalog:manage', 'security:extract', 'orders:list', 'receipts:verify',
        ):
            with self.subTest(route=name):
                response = self.client.get(reverse(name), **self.headers)
                self.assertEqual(response.status_code, 302)
                self.assertIn('login', response['Location'])

    def test_roles_do_not_implicitly_grant_superuser_access(self):
        for role, user in self.users.items():
            self.client.force_login(user)
            self.assertEqual(
                self.client.get(reverse('admin:accounts_user_changelist'), **self.headers).status_code, 302,
            )
            self.assertEqual(
                self.client.get(reverse('catalog:manage'), **self.headers).status_code,
                200 if role == 'OPERADOR' else 403,
            )
            self.assertEqual(
                self.client.get(reverse('orders:list'), **self.headers).status_code,
                200 if role in ('CLIENTE', 'OPERADOR') else 403,
            )
            self.assertEqual(
                self.client.get(reverse('security:extract'), **self.headers).status_code, 403,
            )
        self.client.force_login(self.superuser)
        self.assertEqual(
            self.client.get(reverse('admin:accounts_user_changelist'), **self.headers).status_code, 200,
        )
        self.assertEqual(self.client.get(reverse('security:extract'), **self.headers).status_code, 200)
        self.assertEqual(self.client.get(reverse('catalog:manage'), **self.headers).status_code, 403)

    def test_https_login_session_cookie_and_security_headers(self):
        client = Client(enforce_csrf_checks=True)
        url = reverse('accounts:login')
        response = client.get(url, **self.headers)
        for name, value in {
            'X-Frame-Options': 'DENY',
            'X-Content-Type-Options': 'nosniff',
            'Referrer-Policy': 'same-origin',
            'Cross-Origin-Opener-Policy': 'same-origin',
        }.items():
            self.assertEqual(response[name], value)
        self.assertEqual(client.post(url, {}, **self.headers).status_code, 403)
        response = client.post(url, {
            'username': self.users['CLIENTE'].username,
            'password': self.password,
            'csrfmiddlewaretoken': client.cookies[settings.CSRF_COOKIE_NAME].value,
        }, HTTP_ORIGIN='https://localhost:8443', **self.headers)
        self.assertEqual(response.status_code, 302)
        cookie = response.cookies[settings.SESSION_COOKIE_NAME]
        self.assertTrue(cookie['secure'])
        self.assertTrue(cookie['httponly'])
        self.assertEqual(cookie['samesite'], 'Lax')
        self.assertIn('no-store', response['Cache-Control'])
