from collections import Counter
from contextlib import closing
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import sys
from types import SimpleNamespace
from uuid import UUID


PROJECT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT / 'scripts'))
os.environ.update({
    'DJANGO_SETTINGS_MODULE': 'config.settings',
    'DJANGO_SECRET_KEY': secrets.token_urlsafe(48),
    'DJANGO_DEBUG': 'false',
    'DJANGO_LOCAL_HTTPS': 'true',
    'PYTHONDONTWRITEBYTECODE': '1',
})

import django
from django.conf import settings

database = PROJECT / 'db.sqlite3'
uri = database.resolve().as_uri() + '?mode=ro'
settings.DATABASES = {'default': {
    'ENGINE': 'django.db.backends.sqlite3', 'NAME': uri, 'OPTIONS': {'uri': True},
}}
django.setup()

from django.db import connections
from receipts.crypto import ReceiptConfigurationError, public_key
from receipts.services import verify_stored_receipt
from security.fingerprinting import FingerprintError, read_original
import recovery


def main():
    before = recovery.digest(database)
    counters = Counter()
    missing_names = set()
    missing_key_ids = set()
    with closing(sqlite3.connect(uri, uri=True)) as db:
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        state = recovery.database_state(db)
        for name, expected in db.execute('SELECT pdf,sha256 FROM catalog_product'):
            path = settings.PRIVATE_CATALOG_ROOT / name
            if not path.is_file():
                counters['missing_product_pdf_references'] += 1
                missing_names.add(name)
            else:
                counters['available_product_pdf_references'] += 1
                if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                    raise RuntimeError('Discrepancia de integridad en PDF disponible.')
        query = (
            'SELECT i.pdf_name,i.pdf_sha256,o.status,p.result FROM orders_orderitem i '
            'JOIN orders_order o ON o.id=i.order_id '
            'LEFT JOIN orders_simulatedpayment p ON p.order_id=o.id'
        )
        for name, expected, status, payment in db.execute(query):
            eligible = status == 'PAID' and payment == 'SUCCESS'
            item = SimpleNamespace(pdf_name=name, pdf_sha256=expected)
            if not name or not expected:
                counters['unversioned_order_items'] += 1
                counters['paid_unversioned_order_items'] += int(eligible)
                try:
                    read_original(item)
                except FingerprintError:
                    counters['unversioned_read_original_rejected'] += 1
                else:
                    raise RuntimeError('Se acepto una linea sin version.')
            elif not (settings.PRIVATE_CATALOG_ROOT / name).is_file():
                counters['missing_order_pdf_references'] += 1
                counters['paid_missing_order_pdf_references'] += int(eligible)
                missing_names.add(name)
                try:
                    read_original(item)
                except FingerprintError:
                    counters['missing_read_original_rejected'] += 1
                else:
                    raise RuntimeError('Se acepto un original ausente.')
            else:
                read_original(item)
                counters['available_order_pdf_references_verified'] += 1
        counters['distinct_missing_pdf_files'] = len(missing_names)
        for row in db.execute('SELECT id,payment_id,key_id,body,sha256,signature FROM receipts_receipt'):
            receipt = SimpleNamespace(
                pk=UUID(row[0]), payment_id=row[1], key_id=row[2],
                body=row[3], sha256=row[4], signature=row[5],
            )
            try:
                verify_stored_receipt(receipt)
            except ReceiptConfigurationError:
                if (Path(settings.RECEIPTS_PUBLIC_KEYS_DIR) / (receipt.key_id + '.pem')).is_file():
                    raise
                counters['receipts_unverifiable_missing_public_key'] += 1
                missing_key_ids.add(receipt.key_id)
            else:
                counters['stored_receipts_verified_including_relationships'] += 1
        events = dict(db.execute('SELECT kind,count(*) FROM accounts_securityevent GROUP BY kind'))

    base = Path(os.environ['LOCALAPPDATA']) / 'ProyectoFinalRecuperacion'
    pin = '4d328894e0cefa9a0c81c62996e0578e6924a1d6eabdff42413095cc0b7ff8f5'
    package = base / 'respaldos' / 'backup-20261119-171612-085624-3e582fd6'
    manifest = recovery.verify_package(package, pin, True)
    restored_count = 0
    restored_states = {}
    for name in ('prueba-real-01', 'prueba-real-02', 'prueba-sin-fuentes-03'):
        restored_manifest = recovery.verify_package(base / 'restauraciones' / name, pin, True)
        restored_states[name] = restored_manifest['database']
        restored_count += 1
    try:
        recovery.verify_package(base / 'pruebas' / 'copia-alterada-20261119-1718', pin, True)
    except recovery.RecoveryError:
        altered_rejected = True
    else:
        raise RuntimeError('Se acepto la copia alterada.')
    connections.close_all()
    unchanged = before == recovery.digest(database)
    if not unchanged:
        raise RuntimeError('La base activa cambio durante la consulta; revisar actividad concurrente.')
    print(json.dumps({
        'executed_at': datetime.now().astimezone().isoformat(),
        'database': state, 'availability_and_impact': dict(counters),
        'missing_public_key_ids': sorted(missing_key_ids),
        'configured_public_key': {
            'key_id': settings.RECEIPTS_KEY_ID,
            'rsa_bits': public_key(settings.RECEIPTS_KEY_ID, required=True).key_size,
        },
        'security_events_by_kind': events,
        'configured_https_profile': {
            'debug': settings.DEBUG, 'local_https': settings.LOCAL_HTTPS,
            'secure_session_cookie': settings.SESSION_COOKIE_SECURE,
            'secure_csrf_cookie': settings.CSRF_COOKIE_SECURE,
            'csrf_trusted_origins': settings.CSRF_TRUSTED_ORIGINS,
        },
        'backup_data_files_verified': len(manifest['files']),
        'existing_restorations_reverified': restored_count,
        'restored_database_states': restored_states,
        'existing_altered_copy_rejected': altered_rejected,
        'database_sha256_unchanged': unchanged,
        'scope': 'Only aggregate data; active database opened read-only; no HTTP requests to Django.',
    }, indent=2, ensure_ascii=True))


if __name__ == '__main__':
    main()
