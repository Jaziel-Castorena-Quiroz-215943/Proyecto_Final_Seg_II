import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import time
from datetime import datetime, timezone
from uuid import uuid4

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from dotenv import dotenv_values


PROJECT = Path(__file__).resolve().parent.parent
TABLES = {
    'users': 'accounts_user',
    'products': 'catalog_product',
    'orders': 'orders_order',
    'payments': 'orders_simulatedpayment',
    'receipts': 'receipts_receipt',
    'fingerprints': 'security_downloadfingerprint',
}
SHA256 = re.compile(r'^[0-9a-f]{64}$')
PDF_NAME = re.compile(r'^[0-9a-f]{32}\.pdf$')
KEY_ID = re.compile(r'^[A-Za-z0-9_-]{1,64}$')
MEMBER = re.compile(
    r'^(db\.sqlite3|catalog/[0-9a-f]{32}\.pdf|public_keys/[A-Za-z0-9_-]{1,64}\.pem)$'
)


class RecoveryError(Exception):
    pass


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def reject_links(path, *, missing_ok=False):
    for candidate in (path, *path.parents):
        try:
            info = candidate.lstat()
        except FileNotFoundError:
            if missing_ok:
                continue
            raise
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise RecoveryError('No se permiten enlaces simbolicos ni puntos de reanalisis.')
    if path.is_file() and path.stat().st_nlink != 1:
        raise RecoveryError('No se permiten archivos con enlaces duros.')


def read_database(path):
    reject_links(path)
    connection = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=10)
    connection.enable_load_extension(False)
    connection.execute('PRAGMA trusted_schema=OFF')
    connection.execute('PRAGMA query_only=ON')
    return connection


def database_state(connection):
    if connection.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
        raise RecoveryError('PRAGMA integrity_check no es ok.')
    if connection.execute('PRAGMA foreign_key_check').fetchone() is not None:
        raise RecoveryError('PRAGMA foreign_key_check detecto relaciones invalidas.')
    tables = dict(connection.execute("SELECT name, type FROM sqlite_master WHERE type='table'"))
    if any(tables.get(table) != 'table' for table in TABLES.values()):
        raise RecoveryError('Faltan tablas esperadas de la plataforma.')
    return {
        'counts': {
            label: connection.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
            for label, table in TABLES.items()
        },
        'integrity_check': 'ok',
        'foreign_key_check': [],
    }


def file_inventory(root):
    reject_links(root)
    result = {}
    for path in sorted(root.rglob('*')):
        reject_links(path)
        if path.is_file():
            result[path.relative_to(root).as_posix()] = {
                'size': path.stat().st_size, 'sha256': digest(path),
            }
    return result


def check_public_key(path):
    try:
        key = serialization.load_pem_public_key(path.read_bytes())
    except (ValueError, TypeError) as exc:
        raise RecoveryError('Se encontro un PEM que no es una clave publica valida.') from exc
    if not isinstance(key, rsa.RSAPublicKey) or key.key_size < 2048:
        raise RecoveryError('Clave publica RSA incompatible.')


def source_files(catalog, public):
    files = {}
    for name in file_inventory(catalog):
        if not PDF_NAME.fullmatch(name):
            raise RecoveryError('Archivo inesperado en el catalogo; solo se admiten PDF UUID del proyecto.')
        path = catalog / name
        with path.open('rb') as stream:
            if stream.read(5) != b'%PDF-':
                raise RecoveryError('Un archivo del catalogo no tiene cabecera PDF.')
        files['catalog/' + name] = path
    for name in file_inventory(public):
        if not name.endswith('.pem') or not KEY_ID.fullmatch(name[:-4]):
            raise RecoveryError('Archivo inesperado en el directorio de claves publicas.')
        path = public / name
        check_public_key(path)
        files['public_keys/' + name] = path
    return files


def availability(connection, root):
    references = list(connection.execute('SELECT pdf, sha256 FROM catalog_product'))
    references += list(connection.execute(
        'SELECT pdf_name, pdf_sha256 FROM orders_orderitem '
        'WHERE pdf_name IS NOT NULL AND pdf_sha256 IS NOT NULL'
    ))
    missing = []
    for name, expected in references:
        if not isinstance(name, str) or not PDF_NAME.fullmatch(name):
            raise RecoveryError('Referencia PDF incompatible o insegura en SQLite.')
        if not isinstance(expected, str) or not SHA256.fullmatch(expected):
            raise RecoveryError('Huella PDF invalida en SQLite.')
        path = root / 'catalog' / name
        if not path.is_file():
            missing.append(name)
        elif digest(path) != expected:
            raise RecoveryError('Un PDF disponible no coincide con su huella historica en SQLite.')
    missing_keys = []
    for (key_id,) in connection.execute('SELECT DISTINCT key_id FROM receipts_receipt'):
        if not isinstance(key_id, str) or not KEY_ID.fullmatch(key_id):
            raise RecoveryError('Identificador de clave historica invalido.')
        if not (root / 'public_keys' / (key_id + '.pem')).is_file():
            missing_keys.append(key_id)
    return {
        'missing_pdf_files': sorted(set(missing)),
        'missing_pdf_references': len(missing),
        'unversioned_order_items': connection.execute(
            'SELECT count(*) FROM orders_orderitem WHERE pdf_name IS NULL OR pdf_sha256 IS NULL'
        ).fetchone()[0],
        'missing_public_key_ids': sorted(missing_keys),
    }


def require_gaps_authorized(gaps, allowed):
    if any(gaps.values()) and not allowed:
        raise RecoveryError('Existen faltantes previos. Revise el inventario y autorice --allow-known-gaps explicitamente.')


def member_path(root, name):
    if not isinstance(name, str) or not MEMBER.fullmatch(name):
        raise RecoveryError('Ruta de archivo no permitida en el manifiesto.')
    return root.joinpath(*name.split('/'))


def read_json(path):
    if path.stat().st_size > 2 * 1024 * 1024:
        raise RecoveryError('Manifiesto demasiado grande.')

    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise RecoveryError('Clave JSON duplicada.')
            result[key] = value
        return result

    return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=unique_keys)


def verify_package(root, expected_hash, allow_gaps, *, staging=False):
    reject_links(root)
    if root.name.startswith('.partial-') and not staging:
        raise RecoveryError('No se aceptan respaldos parciales.')
    inventory = file_inventory(root)
    if 'manifest.json' not in inventory or 'COMPLETE' not in inventory:
        raise RecoveryError('Respaldo incompleto: faltan manifiesto o marcador COMPLETE.')
    if not SHA256.fullmatch(expected_hash) or digest(root / 'manifest.json') != expected_hash:
        raise RecoveryError('La huella del manifiesto no coincide con el valor confiable.')
    if (root / 'COMPLETE').read_text(encoding='ascii').strip() != expected_hash:
        raise RecoveryError('Marcador COMPLETE invalido.')
    manifest = read_json(root / 'manifest.json')
    if not isinstance(manifest, dict) or set(manifest) != {
        'format', 'created_at', 'files', 'database', 'known_gaps', 'source_database_unchanged',
    } or manifest['format'] != 'platform-backup-v1':
        raise RecoveryError('Formato de manifiesto no compatible.')
    entries = manifest['files']
    if not isinstance(entries, list):
        raise RecoveryError('Lista de archivos invalida.')
    expected_names = set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {'path', 'size', 'sha256'}:
            raise RecoveryError('Entrada de manifiesto invalida.')
        name = entry['path']
        path = member_path(root, name)
        if name.casefold() in expected_names:
            raise RecoveryError('Ruta repetida en el manifiesto.')
        expected_names.add(name.casefold())
        if type(entry['size']) is not int or entry['size'] < 0:
            raise RecoveryError('Tamano de archivo invalido.')
        if not isinstance(entry['sha256'], str) or not SHA256.fullmatch(entry['sha256']):
            raise RecoveryError('Formato de huella SHA-256 invalido.')
        if inventory.get(name) != {'size': entry['size'], 'sha256': entry['sha256']}:
            raise RecoveryError('Archivo ausente o alterado respecto al manifiesto.')
        if name.startswith('public_keys/'):
            check_public_key(path)
    if expected_names | {'manifest.json', 'complete'} != {name.casefold() for name in inventory}:
        raise RecoveryError('El respaldo contiene archivos no declarados.')
    if 'db.sqlite3' not in expected_names:
        raise RecoveryError('El respaldo no contiene SQLite.')
    with closing(read_database(root / 'db.sqlite3')) as connection:
        if database_state(connection) != manifest['database']:
            raise RecoveryError('La base no coincide con el estado registrado.')
        gaps = availability(connection, root)
    if gaps != manifest['known_gaps'] or manifest['source_database_unchanged'] is not True:
        raise RecoveryError('Los faltantes o el estado del origen no coinciden con el manifiesto.')
    require_gaps_authorized(gaps, allow_gaps)
    return manifest


def current_sid():
    result = subprocess.run(
        ['whoami.exe', '/user', '/fo', 'csv', '/nh'], capture_output=True, check=True,
    )
    match = re.search(rb'S-1-\d+(?:-\d+)+', result.stdout)
    if match is None:
        raise RecoveryError('No se pudo identificar el SID del usuario actual.')
    return match.group().decode('ascii')


def protected_directory(path):
    sid = current_sid()
    if not path.exists():
        path.mkdir()
        result = subprocess.run(
            ['icacls.exe', str(path), '/inheritance:r', '/grant:r',
             f'*{sid}:(OI)(CI)F', '*S-1-5-18:(OI)(CI)F'],
            capture_output=True,
        )
        if result.returncode:
            raise RecoveryError('No se pudieron restringir los permisos del directorio nuevo.')
    reject_links(path)
    literal = str(path).replace("'", "''")
    check_acl = (
        f"$a=Get-Acl -LiteralPath '{literal}'; "
        "if(-not $a.AreAccessRulesProtected){exit 1}; "
        "foreach($r in $a.Access){"
        "$s=$r.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value; "
        f"if($s -notin @('{sid}','S-1-5-18') -or $r.AccessControlType -ne 'Allow'){{exit 1}}"
        "}; exit 0"
    )
    result = subprocess.run(
        ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', check_acl],
        capture_output=True,
    )
    if result.returncode:
        raise RecoveryError('ACL no restringida al usuario actual y SYSTEM; no se modificaron permisos existentes.')


def configuration(*, require_exists=True):
    values = dotenv_values(PROJECT / '.env')

    def directory(name):
        value = os.environ.get(name, values.get(name))
        if not value or not Path(value).is_absolute():
            raise RecoveryError(f'Falta una ruta absoluta en {name}.')
        path = Path(value)
        reject_links(path, missing_ok=not require_exists)
        return path.resolve()

    return directory('DJANGO_PRIVATE_CATALOG_ROOT'), directory('DJANGO_RECEIPTS_PUBLIC_KEYS_DIR')


def storage(kind):
    local = os.environ.get('LOCALAPPDATA')
    if not local or not Path(local).is_absolute():
        raise RecoveryError('LOCALAPPDATA no es una ruta absoluta.')
    base = Path(local) / 'ProyectoFinalRecuperacion'
    catalog, public = configuration(require_exists=False)
    for path in (base, base / kind):
        if any(path.resolve().is_relative_to(root) for root in (PROJECT, catalog, public)):
            raise RecoveryError('El destino debe estar separado del proyecto y de los datos originales.')
        if any((parent / '.git').exists() for parent in (path, *path.parents)):
            raise RecoveryError('El destino no puede estar dentro de un repositorio Git.')
        protected_directory(path)
    return base / kind


def identifier(prefix):
    return prefix + datetime.now().astimezone().strftime('%Y%m%d-%H%M%S-%f') + '-' + uuid4().hex[:8]


def source_database_hashes():
    paths = [PROJECT / 'db.sqlite3', PROJECT / 'db.sqlite3-wal']
    return {path.name: digest(path) for path in paths if path.is_file()}


def write_json(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, ensure_ascii=True)
        stream.write('\n')


def backup(allow_gaps):
    catalog, public = configuration()
    output = storage('respaldos')
    name = identifier('backup-')
    partial = output / ('.partial-' + name)
    protected_directory(partial)
    (partial / 'catalog').mkdir()
    (partial / 'public_keys').mkdir()
    before = source_database_hashes()
    files = source_files(catalog, public)
    initial = {name: digest(path) for name, path in files.items()}
    deadline = time.monotonic() + 60

    def progress(status, remaining, total):
        if time.monotonic() > deadline:
            raise RecoveryError('SQLite no pudo completar el snapshot en 60 segundos.')

    with closing(read_database(PROJECT / 'db.sqlite3')) as source:
        source.execute('BEGIN')
        original_state = database_state(source)
        with closing(sqlite3.connect(partial / 'db.sqlite3')) as destination:
            source.backup(destination, pages=256, sleep=0.1, progress=progress)
        source.rollback()
    for relative, path in files.items():
        reject_links(path)
        target = member_path(partial, relative)
        with path.open('rb') as source, target.open('xb') as destination:
            shutil.copyfileobj(source, destination)
        if digest(target) != initial[relative]:
            raise RecoveryError('Un archivo cambio durante la copia; el respaldo queda parcial.')
    if source_database_hashes() != before:
        raise RecoveryError('SQLite cambio durante la prueba; repita sin escrituras concurrentes.')
    final_files = source_files(catalog, public)
    if {name: digest(path) for name, path in final_files.items()} != initial:
        raise RecoveryError('El almacenamiento privado cambio durante el respaldo.')
    with closing(read_database(partial / 'db.sqlite3')) as connection:
        if database_state(connection) != original_state:
            raise RecoveryError('El snapshot SQLite no coincide con el origen.')
        gaps = availability(connection, partial)
    require_gaps_authorized(gaps, allow_gaps)
    manifest = {
        'format': 'platform-backup-v1',
        'created_at': datetime.now(timezone.utc).isoformat(),
        'files': [
            {'path': name, **details} for name, details in file_inventory(partial).items()
        ],
        'database': original_state,
        'known_gaps': gaps,
        'source_database_unchanged': True,
    }
    write_json(partial / 'manifest.json', manifest)
    manifest_hash = digest(partial / 'manifest.json')
    with (partial / 'COMPLETE').open('x', encoding='ascii') as stream:
        stream.write(manifest_hash + '\n')
    target = output / name
    verify_package(partial, manifest_hash, allow_gaps, staging=True)
    partial.rename(target)
    return {
        'backup_path': str(target), 'manifest_sha256': manifest_hash,
        'counts': original_state['counts'], 'private_files': len(initial) - sum(
            name.startswith('public_keys/') for name in initial
        ),
        'known_missing_pdf_references': gaps['missing_pdf_references'],
        'known_missing_public_keys': len(gaps['missing_public_key_ids']),
        'status': 'VERIFICADO_CON_LIMITACIONES_PREEXISTENTES' if any(gaps.values()) else 'VERIFICADO',
    }


def restore(backup_path, expected_hash, name, allow_gaps):
    package = Path(backup_path).absolute()
    manifest = verify_package(package, expected_hash.lower(), allow_gaps)
    root = storage('restauraciones')
    if name is None:
        name = identifier('restore-')
    if not KEY_ID.fullmatch(name):
        raise RecoveryError('Nombre de restauracion invalido.')
    destination = root / name
    partial = root / ('.partial-' + name)
    if destination.exists() or partial.exists():
        raise RecoveryError('El destino ya existe; nunca se sobrescribe una restauracion.')
    protected_directory(partial)
    for folder in ('catalog', 'public_keys'):
        (partial / folder).mkdir()
    for entry in manifest['files']:
        source = member_path(package, entry['path'])
        target = member_path(partial, entry['path'])
        reject_links(source)
        with source.open('rb') as original, target.open('xb') as restored:
            shutil.copyfileobj(original, restored)
        if target.stat().st_size != entry['size'] or digest(target) != entry['sha256']:
            raise RecoveryError('El archivo cambio entre verificacion y restauracion.')
    shutil.copyfile(package / 'manifest.json', partial / 'manifest.json')
    shutil.copyfile(package / 'COMPLETE', partial / 'COMPLETE')
    verify_package(partial, expected_hash.lower(), allow_gaps, staging=True)
    partial.rename(destination)
    return {
        'restored_path': str(destination), 'manifest_sha256': expected_hash.lower(),
        'database': manifest['database'],
        'private_files': sum(entry['path'].startswith('catalog/') for entry in manifest['files']),
        'known_missing_pdf_references': manifest['known_gaps']['missing_pdf_references'],
        'status': 'RESTAURADO_CON_LIMITACIONES_PREEXISTENTES' if any(manifest['known_gaps'].values()) else 'RESTAURADO',
    }


def main():
    parser = argparse.ArgumentParser(description='Respaldo y restauracion de datos, sin importar codigo del respaldo.')
    subparsers = parser.add_subparsers(dest='operation', required=True)
    backup_parser = subparsers.add_parser('backup')
    backup_parser.add_argument('--allow-known-gaps', action='store_true')
    restore_parser = subparsers.add_parser('restore')
    restore_parser.add_argument('--backup-path', required=True)
    restore_parser.add_argument('--expected-manifest-sha256', required=True)
    restore_parser.add_argument('--name')
    restore_parser.add_argument('--allow-known-gaps', action='store_true')
    arguments = parser.parse_args()
    try:
        if arguments.operation == 'backup':
            result = backup(arguments.allow_known_gaps)
        else:
            result = restore(
                arguments.backup_path, arguments.expected_manifest_sha256,
                arguments.name, arguments.allow_known_gaps,
            )
    except (RecoveryError, OSError, sqlite3.Error, ValueError, subprocess.SubprocessError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
