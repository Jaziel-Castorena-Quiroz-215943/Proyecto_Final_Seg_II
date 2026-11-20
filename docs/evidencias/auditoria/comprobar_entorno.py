from contextlib import closing
from datetime import datetime
import http.client
import json
import os
from pathlib import Path
import secrets
import ssl
import socket
import subprocess
import sys
import tempfile

from dotenv import dotenv_values


PROJECT = Path(__file__).resolve().parents[3]


def main():
    configuration = dotenv_values(PROJECT / '.env')
    example = dotenv_values(PROJECT / '.env.example')
    sensitive = ('DJANGO_SECRET_KEY', 'DJANGO_RECEIPTS_PRIVATE_KEY_PASSWORD')
    results = {
        'executed_at': datetime.now().astimezone().isoformat(),
        'dotenv_contains_secret_values': any(configuration.get(name) for name in sensitive),
        'example_contains_secret_values': any(example.get(name) for name in sensitive),
    }
    if results['dotenv_contains_secret_values'] or results['example_contains_secret_values']:
        raise RuntimeError('Se encontro un valor secreto en un archivo de entorno.')
    results['configured_profile'] = {
        name: configuration.get(name) for name in
        ('DJANGO_DEBUG', 'DJANGO_LOCAL_HTTPS', 'DJANGO_ALLOWED_HOSTS', 'DJANGO_RECEIPTS_KEY_ID')
    }
    for label, name in (
        ('catalog_outside_project', 'DJANGO_PRIVATE_CATALOG_ROOT'),
        ('rsa_private_outside_project', 'DJANGO_RECEIPTS_PRIVATE_KEY_PATH'),
    ):
        results[label] = not Path(configuration[name]).resolve().is_relative_to(PROJECT)

    git_status = subprocess.run(
        ['git', '-C', str(PROJECT), 'rev-parse', '--show-toplevel'], capture_output=True,
    )
    results['active_git_repository_available'] = git_status.returncode == 0
    with tempfile.TemporaryDirectory(prefix='audit-git-rules-') as temporary:
        subprocess.run(['git', 'init', '--quiet', temporary], check=True, capture_output=True)
        git = ['git', '-c', 'core.excludesFile=NUL', '--git-dir=' + str(Path(temporary) / '.git'),
               '--work-tree=' + str(PROJECT), 'check-ignore', '--no-index', '--quiet', '--']
        cases = {
            '.env': True, 'password.dpapi': True, 'privada.pem': True,
            'private-key.pem': True, 'db.sqlite3': True, 'db.sqlite3-wal': True,
            'catalogo\\example.pdf': True, 'archivos_privados\\example.pdf': True,
            'config\\__pycache__\\settings.pyc': True, 'venv\\Scripts\\python.exe': True,
            'staticfiles\\example.css': True,
            '.env.example': False, 'publicas\\rsa-demo-2026.pem': False,
        }
        for name, ignored in cases.items():
            code = subprocess.run(git + [name], capture_output=True).returncode
            if code != (0 if ignored else 1):
                raise RuntimeError('No coincide una regla de exclusion Git.')
        results['git_ignore_rules_verified'] = len(cases)
        results['public_verification_keys_distributable'] = True

    public_text_files = 0
    for directory, folders, names in os.walk(PROJECT):
        folders[:] = [name for name in folders if name not in
                      ('venv', '.venv', '__pycache__', 'staticfiles', '.git')]
        for name in names:
            path = Path(directory) / name
            if path.suffix not in ('.py', '.ps1', '.md', '.txt', '.html', '.css', '.js', '.example'):
                continue
            text = path.read_text(encoding='utf-8-sig')
            if any(line.startswith('-----BEGIN ') and 'PRIVATE KEY-----' in line for line in text.splitlines()):
                raise RuntimeError('Se encontro material PEM privado en un archivo de texto publico.')
            public_text_files += 1
    results['public_text_files_checked_for_private_pem_blocks'] = public_text_files
    results['scope_of_secret_check'] = 'No DPAPI decryption, secret-value matching or Git history scan.'

    ssh_path = Path(os.environ['PROGRAMDATA']) / 'ssh' / 'sshd_config'
    allowed = ('port', 'listenaddress', 'pubkeyauthentication',
               'passwordauthentication', 'kbdinteractiveauthentication')
    ssh = {}
    for line in ssh_path.read_text(encoding='utf-8-sig').splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2 and parts[0].lower() in allowed:
            ssh[parts[0].lower()] = parts[1]
    results['ssh_configuration_read'] = ssh
    command = (
        "Get-NetTCPConnection -State Listen | "
        "Where-Object {$_.LocalPort -in @(22,8000,8080,8443)} | "
        "Select-Object LocalAddress,LocalPort | ConvertTo-Json -Compress"
    )
    listeners = subprocess.run(
        ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', command],
        capture_output=True, encoding='utf-8', check=True,
    )
    results['local_listeners'] = json.loads(listeners.stdout)
    if any(item['LocalAddress'] != '127.0.0.1' for item in results['local_listeners']):
        raise RuntimeError('Se observo un enlace de servicio fuera de loopback.')

    ca = Path(os.environ['APPDATA']) / 'Caddy' / 'pki' / 'authorities' / 'local' / 'root.crt'
    if not ca.is_file():
        results['tls_handshake'] = 'PENDING_PUBLIC_CA_NOT_FOUND'
    else:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations(cafile=str(ca))
        with socket.create_connection(('127.0.0.1', 8443), timeout=5) as raw:
            with context.wrap_socket(raw, server_hostname='localhost') as tls:
                results['tls_handshake'] = {
                    'explicit_ca_and_hostname_validated': True,
                    'negotiated_version': tls.version(),
                }
        untrusted = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        try:
            with socket.create_connection(('127.0.0.1', 8443), timeout=5) as raw:
                with untrusted.wrap_socket(raw, server_hostname='localhost'):
                    raise RuntimeError('Se acepto TLS sin la CA confiable.')
        except ssl.SSLCertVerificationError:
            results['untrusted_ca_rejected'] = True

    with closing(http.client.HTTPConnection('127.0.0.1', 8080, timeout=5)) as client:
        client.request('GET', '/', headers={'Host': 'localhost:8080'})
        response = client.getresponse()
        results['caddy_http_redirect'] = {
            'status': response.status,
            'expected_location': response.getheader('Location') == 'https://localhost:8443/',
        }
        response.read()
        if response.status != 308 or not results['caddy_http_redirect']['expected_location']:
            raise RuntimeError('La redireccion local de Caddy no coincide.')

    env = os.environ.copy()
    env.update({
        'DJANGO_DEBUG': 'false', 'DJANGO_LOCAL_HTTPS': 'true',
        'DJANGO_SECRET_KEY': secrets.token_urlsafe(48), 'PYTHONDONTWRITEBYTECODE': '1',
    })
    check = subprocess.run(
        [sys.executable, '-B', str(PROJECT / 'manage.py'), 'check'], cwd=PROJECT,
        env=env, capture_output=True, encoding='utf-8',
    )
    if check.returncode:
        raise RuntimeError('manage.py check con perfil HTTPS fallo.')
    results['django_check_https_exit_code'] = check.returncode
    results['django_check_scope'] = 'Configured HTTPS with ephemeral audit-only secret; no production DPAPI loaded.'
    print(json.dumps(results, indent=2, ensure_ascii=True))


if __name__ == '__main__':
    main()
