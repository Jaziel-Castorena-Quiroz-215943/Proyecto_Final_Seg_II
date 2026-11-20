import tempfile
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.test import override_settings


class ReceiptKeysMixin:
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        directory = tempfile.TemporaryDirectory(prefix='receipt-tests-')
        cls.addClassCleanup(directory.cleanup)
        root = Path(directory.name)
        private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        private_path = root / 'private.pem'
        private_path.write_bytes(private.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.BestAvailableEncryption(b'test-only-password'),
        ))
        public_dir = root / 'public'
        public_dir.mkdir()
        (public_dir / 'test-key.pem').write_bytes(private.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
        ))
        override = override_settings(
            RECEIPTS_PRIVATE_KEY_PATH=str(private_path),
            RECEIPTS_PRIVATE_KEY_PASSWORD='test-only-password',
            RECEIPTS_PUBLIC_KEYS_DIR=str(public_dir),
            RECEIPTS_KEY_ID='test-key',
        )
        override.enable()
        cls.addClassCleanup(override.disable)
