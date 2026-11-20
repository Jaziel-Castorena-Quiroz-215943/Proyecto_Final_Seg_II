from contextlib import closing
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import recovery


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.project = self.root / 'project'
        self.catalog = self.root / 'catalog'
        self.public = self.root / 'public'
        self.backups = self.root / 'backups'
        self.restores = self.root / 'restores'
        for path in (self.project, self.catalog, self.public, self.backups, self.restores):
            path.mkdir()
        self.pdf_name = 'a' * 32 + '.pdf'
        (self.catalog / self.pdf_name).write_bytes(b'%PDF-1.4\nrecovery-test')
        with closing(sqlite3.connect(self.project / 'db.sqlite3')) as db, db:
            db.executescript('''
                CREATE TABLE accounts_user (id INTEGER PRIMARY KEY);
                CREATE TABLE catalog_product (id INTEGER PRIMARY KEY, pdf TEXT, sha256 TEXT);
                CREATE TABLE orders_order (id INTEGER PRIMARY KEY, user_id INTEGER REFERENCES accounts_user(id));
                CREATE TABLE orders_simulatedpayment (id INTEGER PRIMARY KEY);
                CREATE TABLE receipts_receipt (id INTEGER PRIMARY KEY, key_id TEXT);
                CREATE TABLE security_downloadfingerprint (id INTEGER PRIMARY KEY);
                CREATE TABLE orders_orderitem (id INTEGER PRIMARY KEY, pdf_name TEXT, pdf_sha256 TEXT);
                INSERT INTO accounts_user VALUES (1);
                INSERT INTO orders_order VALUES (1, 1);
            ''')
            db.execute(
                'INSERT INTO catalog_product VALUES (1, ?, ?)',
                (self.pdf_name, recovery.digest(self.catalog / self.pdf_name)),
            )
        for name, value in (
            ('PROJECT', self.project),
            ('configuration', lambda: (self.catalog, self.public)),
            ('storage', lambda kind: self.backups if kind == 'respaldos' else self.restores),
            ('protected_directory', lambda path: path.mkdir()),
        ):
            context = patch.object(recovery, name, value)
            context.start()
            self.addCleanup(context.stop)

    def make_backup(self, allow=False):
        result = recovery.backup(allow)
        return Path(result['backup_path']), result['manifest_sha256']

    def rewrite_manifest(self, package, edit):
        path = package / 'manifest.json'
        manifest = json.loads(path.read_text(encoding='utf-8'))
        edit(manifest)
        path.write_text(json.dumps(manifest), encoding='utf-8')
        digest = recovery.digest(path)
        (package / 'COMPLETE').write_text(digest + '\n', encoding='ascii')
        return digest

    def test_roundtrip_is_repeatable_without_overwriting_source_or_destination(self):
        original = recovery.digest(self.project / 'db.sqlite3')
        package, digest = self.make_backup()
        for name in ('first', 'second'):
            result = recovery.restore(str(package), digest, name, False)
            restored = Path(result['restored_path'])
            self.assertEqual(recovery.digest(restored / 'db.sqlite3'), recovery.digest(package / 'db.sqlite3'))
            self.assertEqual((restored / 'catalog' / self.pdf_name).read_bytes(), (self.catalog / self.pdf_name).read_bytes())
        with self.assertRaisesRegex(recovery.RecoveryError, 'destino ya existe'):
            recovery.restore(str(package), digest, 'first', False)
        self.assertEqual(recovery.digest(self.project / 'db.sqlite3'), original)

    def test_altered_or_incomplete_copy_is_rejected_without_touching_valid_backup(self):
        package, digest = self.make_backup()
        for kind in ('altered', 'missing', 'extra', 'incomplete'):
            with self.subTest(kind=kind):
                copy = self.root / kind
                excluded = (self.pdf_name,) if kind == 'missing' else ('COMPLETE',) if kind == 'incomplete' else ()
                shutil.copytree(package, copy, ignore=shutil.ignore_patterns(*excluded))
                if kind == 'altered':
                    with (copy / 'catalog' / self.pdf_name).open('ab') as stream:
                        stream.write(b'changed')
                elif kind == 'extra':
                    (copy / 'untrusted.py').write_text('raise RuntimeError("must not execute")', encoding='ascii')
                with self.assertRaises(recovery.RecoveryError):
                    recovery.restore(str(copy), digest, kind, False)
                self.assertFalse((self.restores / kind).exists())
        recovery.verify_package(package, digest, False)

    def test_manifest_paths_and_pin_are_validated_even_if_hashes_are_recomputed(self):
        package, digest = self.make_backup()
        with self.assertRaisesRegex(recovery.RecoveryError, 'huella del manifiesto'):
            recovery.restore(str(package), '0' * 64, 'wrong-pin', False)
        for number, name in enumerate(('../outside.pdf', 'C:\\outside.pdf', 'catalog/../outside.pdf', 'catalog/x:stream.pdf')):
            copy = self.root / f'path-{number}'
            shutil.copytree(package, copy)
            altered_hash = self.rewrite_manifest(copy, lambda m: m['files'][0].update(path=name))
            with self.assertRaisesRegex(recovery.RecoveryError, 'Ruta de archivo no permitida'):
                recovery.restore(str(copy), altered_hash, f'path-{number}', False)
        recovery.verify_package(package, digest, False)

    def test_known_gaps_require_explicit_permission_at_backup_and_restore(self):
        with closing(sqlite3.connect(self.project / 'db.sqlite3')) as db, db:
            db.execute('INSERT INTO orders_orderitem VALUES (1, NULL, NULL)')
            db.execute('INSERT INTO receipts_receipt VALUES (1, ?)', ('missing-key',))
        with self.assertRaisesRegex(recovery.RecoveryError, 'faltantes previos'):
            recovery.backup(False)
        package, digest = self.make_backup(allow=True)
        with self.assertRaisesRegex(recovery.RecoveryError, 'faltantes previos'):
            recovery.restore(str(package), digest, 'strict', False)
        result = recovery.restore(str(package), digest, 'authorized', True)
        self.assertEqual(result['status'], 'RESTAURADO_CON_LIMITACIONES_PREEXISTENTES')

    def test_invalid_relationships_are_rejected(self):
        with closing(sqlite3.connect(self.project / 'db.sqlite3')) as db, db:
            db.execute('INSERT INTO orders_order VALUES (2, 999)')
        with self.assertRaisesRegex(recovery.RecoveryError, 'relaciones invalidas'):
            recovery.backup(False)


if __name__ == '__main__':
    unittest.main()
