import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from shutil import copyfile

from django.conf import settings
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpResponse
from django.test import Client, RequestFactory, SimpleTestCase, override_settings
from django.urls import reverse


class DotenvSettingsTests(SimpleTestCase):
    def load_settings(self, directory, **overrides):
        env = {name: value for name, value in os.environ.items() if not name.startswith('DJANGO_')}
        env.update(overrides)
        code = (
            'import json, runpy, sys; s = runpy.run_path(sys.argv[1]); '
            'print(json.dumps([s["DEBUG"], s["LOCAL_HTTPS"], s["ALLOWED_HOSTS"]]))'
        )
        return subprocess.run(
            [sys.executable, '-B', '-c', code, str(directory / 'config' / 'settings.py')],
            cwd=directory.parent, env=env, capture_output=True, text=True, check=False,
        )

    def test_dotenv_is_loaded_from_project_root_not_working_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'config').mkdir()
            copyfile(settings.BASE_DIR / 'config' / 'settings.py', root / 'config' / 'settings.py')
            (root / '.env').write_text(
                'DJANGO_DEBUG=false\nDJANGO_LOCAL_HTTPS=true\n'
                'DJANGO_SECRET_KEY=test-only-secret\nDJANGO_ALLOWED_HOSTS=localhost\n',
                encoding='utf-8',
            )
            result = self.load_settings(root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), [False, True, ['localhost']])

    def test_existing_environment_takes_precedence_over_dotenv(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'config').mkdir()
            copyfile(settings.BASE_DIR / 'config' / 'settings.py', root / 'config' / 'settings.py')
            (root / '.env').write_text(
                'DJANGO_DEBUG=false\nDJANGO_LOCAL_HTTPS=true\nDJANGO_ALLOWED_HOSTS=example.invalid\n',
                encoding='utf-8',
            )
            result = self.load_settings(
                root, DJANGO_DEBUG='true', DJANGO_LOCAL_HTTPS='false', DJANGO_ALLOWED_HOSTS='localhost',
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), [True, False, ['localhost']])


class LocalHTTPSSettingsTests(SimpleTestCase):
    def settings_process(self, local_https, debug):
        env = os.environ.copy()
        env.update({
            'DJANGO_LOCAL_HTTPS': local_https,
            'DJANGO_DEBUG': debug,
            'DJANGO_SECRET_KEY': 'test-only-secret-key',
            'DJANGO_ALLOWED_HOSTS': 'localhost',
        })
        code = (
            'import json; from config import settings as s; '
            'print(json.dumps({'
            '"local": s.LOCAL_HTTPS, "debug": s.DEBUG, '
            '"proxy": getattr(s, "SECURE_PROXY_SSL_HEADER", None), '
            '"redirect": getattr(s, "SECURE_SSL_REDIRECT", False), '
            '"session": s.SESSION_COOKIE_SECURE, "csrf": s.CSRF_COOKIE_SECURE, '
            '"forwarded_host": getattr(s, "USE_X_FORWARDED_HOST", False), '
            '"hsts": getattr(s, "SECURE_HSTS_SECONDS", 0), '
            '"static": str(getattr(s, "STATIC_ROOT", ""))'
            '}))'
        )
        return subprocess.run([sys.executable, '-c', code], env=env, capture_output=True, text=True, check=False)

    def test_https_profile_is_opt_in(self):
        result = self.settings_process('false', 'true')
        self.assertEqual(result.returncode, 0, result.stderr)
        values = json.loads(result.stdout)
        self.assertFalse(values['local'])
        self.assertIsNone(values['proxy'])
        self.assertFalse(values['redirect'])
        self.assertFalse(values['session'])
        self.assertFalse(values['csrf'])

    def test_https_profile_configures_proxy_redirect_and_secure_cookies(self):
        result = self.settings_process('true', 'false')
        self.assertEqual(result.returncode, 0, result.stderr)
        values = json.loads(result.stdout)
        self.assertEqual(values['proxy'], ['HTTP_X_FORWARDED_PROTO', 'https'])
        self.assertTrue(values['redirect'])
        self.assertTrue(values['session'])
        self.assertTrue(values['csrf'])
        self.assertFalse(values['forwarded_host'])
        self.assertEqual(values['hsts'], 0)
        self.assertEqual(values['static'], str(settings.BASE_DIR / 'staticfiles'))

    def test_https_profile_rejects_debug(self):
        result = self.settings_process('true', 'true')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('DJANGO_LOCAL_HTTPS requiere DJANGO_DEBUG=false', result.stderr)


@override_settings(
    DEBUG=False,
    ALLOWED_HOSTS=['localhost'],
    SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO', 'https'),
    SECURE_SSL_REDIRECT=True,
    SESSION_COOKIE_SECURE=True,
    CSRF_COOKIE_SECURE=True,
    CSRF_TRUSTED_ORIGINS=[],
)
class LocalHTTPSBehaviorTests(SimpleTestCase):
    def test_https_proxy_does_not_redirect_and_http_does(self):
        client = Client()
        url = reverse('accounts:login')
        insecure = client.get(url, HTTP_HOST='localhost:8443', HTTP_X_FORWARDED_PROTO='http')
        self.assertEqual(insecure.status_code, 301)
        self.assertEqual(insecure['Location'], 'https://localhost:8443' + url)
        secure = client.get(url, HTTP_HOST='localhost:8443', HTTP_X_FORWARDED_PROTO='https')
        self.assertEqual(secure.status_code, 200)

    def test_csrf_requires_token_and_same_secure_origin(self):
        client = Client(enforce_csrf_checks=True)
        url = reverse('accounts:login')
        headers = {'HTTP_HOST': 'localhost:8443', 'HTTP_X_FORWARDED_PROTO': 'https'}
        client.get(url, **headers)
        cookie = client.cookies[settings.CSRF_COOKIE_NAME]
        self.assertTrue(cookie['secure'])
        token = cookie.value
        allowed = client.post(url, {'csrfmiddlewaretoken': token}, HTTP_ORIGIN='https://localhost:8443', **headers)
        self.assertEqual(allowed.status_code, 200)
        denied = client.post(url, {'csrfmiddlewaretoken': token}, HTTP_ORIGIN='https://evil.example', **headers)
        self.assertEqual(denied.status_code, 403)
        missing = client.post(url, {}, HTTP_ORIGIN='https://localhost:8443', **headers)
        self.assertEqual(missing.status_code, 403)

    @override_settings(SESSION_ENGINE='django.contrib.sessions.backends.signed_cookies')
    def test_session_cookie_is_secure(self):
        request = RequestFactory().get('/', HTTP_HOST='localhost:8443', HTTP_X_FORWARDED_PROTO='https')
        middleware = SessionMiddleware(lambda request: HttpResponse())
        middleware.process_request(request)
        request.session['test'] = 'value'
        response = middleware.process_response(request, HttpResponse())
        self.assertTrue(response.cookies[settings.SESSION_COOKIE_NAME]['secure'])
