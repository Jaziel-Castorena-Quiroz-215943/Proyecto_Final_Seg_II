import base64
import binascii
import hashlib
import hmac
import json
import re
from pathlib import Path

from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from django.conf import settings


ALGORITHM = 'RSA-PSS-SHA256'
FORMAT = 'receipt-v1'
KEY_ID_PATTERN = re.compile(r'^[A-Za-z0-9_-]{1,64}$')


class ReceiptConfigurationError(Exception):
    pass


class InvalidReceipt(Exception):
    pass


def canonical_json(body):
    return json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def public_key(key_id, *, required=False):
    if not isinstance(key_id, str) or not KEY_ID_PATTERN.fullmatch(key_id):
        raise InvalidReceipt('Identificador de clave inválido.')
    directory = settings.RECEIPTS_PUBLIC_KEYS_DIR
    if not directory or not Path(directory).is_absolute():
        raise ReceiptConfigurationError('Directorio de claves públicas no configurado.')
    try:
        key = serialization.load_pem_public_key((Path(directory) / f'{key_id}.pem').read_bytes())
    except FileNotFoundError as exc:
        if required:
            raise ReceiptConfigurationError('Falta una clave pública necesaria para verificar el comprobante.') from exc
        raise InvalidReceipt('Clave pública desconocida.') from exc
    except (OSError, ValueError, TypeError, UnsupportedAlgorithm) as exc:
        raise ReceiptConfigurationError('No se pudo cargar la clave pública.') from exc
    if not isinstance(key, rsa.RSAPublicKey) or key.key_size < 2048:
        raise ReceiptConfigurationError('La clave pública debe ser RSA de al menos 2048 bits.')
    return key


def signing_key():
    key_id = settings.RECEIPTS_KEY_ID
    if not isinstance(key_id, str) or not KEY_ID_PATTERN.fullmatch(key_id):
        raise ReceiptConfigurationError('Identificador de clave no configurado o inválido.')
    path = settings.RECEIPTS_PRIVATE_KEY_PATH
    if not path or not Path(path).is_absolute():
        raise ReceiptConfigurationError('Ruta absoluta de clave privada no configurada.')
    resolved = Path(path).resolve()
    if resolved.is_relative_to(settings.BASE_DIR.resolve()):
        raise ReceiptConfigurationError('La clave privada debe estar fuera del proyecto.')
    password = settings.RECEIPTS_PRIVATE_KEY_PASSWORD
    try:
        private = serialization.load_pem_private_key(
            resolved.read_bytes(), password=password.encode('utf-8') if password else None,
        )
    except (OSError, ValueError, TypeError, UnsupportedAlgorithm) as exc:
        raise ReceiptConfigurationError('No se pudo cargar la clave privada.') from exc
    if not isinstance(private, rsa.RSAPrivateKey) or private.key_size < 2048:
        raise ReceiptConfigurationError('La clave privada debe ser RSA de al menos 2048 bits.')
    try:
        public = public_key(key_id)
    except InvalidReceipt as exc:
        raise ReceiptConfigurationError('Falta la clave pública de firma.') from exc
    if private.public_key().public_numbers() != public.public_numbers():
        raise ReceiptConfigurationError('Las claves pública y privada no coinciden.')
    return key_id, private


def sign_body(body, private):
    data = canonical_json(body).encode('utf-8')
    signature = private.sign(
        data, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256(),
    )
    return hashlib.sha256(data).hexdigest(), base64.b64encode(signature).decode('ascii')


def verify_envelope(envelope, *, trusted_record=False):
    if not isinstance(envelope, dict) or set(envelope) != {'body', 'sha256', 'signature'}:
        raise InvalidReceipt('Formato de comprobante inválido.')
    body = envelope['body']
    if not isinstance(body, dict) or body.get('format') != FORMAT or body.get('algorithm') != ALGORITHM:
        raise InvalidReceipt('Formato o algoritmo no compatible.')
    digest, signature = envelope['sha256'], envelope['signature']
    if not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest) or not isinstance(signature, str):
        raise InvalidReceipt('Firma o resumen inválidos.')
    try:
        data = canonical_json(body).encode('utf-8')
        signature_bytes = base64.b64decode(signature, validate=True)
    except (ValueError, TypeError, binascii.Error, UnicodeError) as exc:
        raise InvalidReceipt('Contenido o firma inválidos.') from exc
    if not hmac.compare_digest(hashlib.sha256(data).hexdigest(), digest):
        raise InvalidReceipt('El contenido fue modificado.')
    key = public_key(body.get('key_id'), required=trusted_record)
    try:
        key.verify(
            signature_bytes, data,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
            hashes.SHA256(),
        )
    except InvalidSignature as exc:
        raise InvalidReceipt('La firma no es válida.') from exc
    return body
