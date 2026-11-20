from django.conf import settings
from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models
from django.db.models.functions import Lower


class AccountManager(UserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('role', User.Role.ADMINISTRADOR)
        return super().create_superuser(username, email, password, **extra_fields)


class User(AbstractUser):
    class Role(models.TextChoices):
        CLIENTE = 'CLIENTE', 'Cliente'
        OPERADOR = 'OPERADOR', 'Operador'
        ADMINISTRADOR = 'ADMINISTRADOR', 'Administrador'

    email = models.EmailField('correo electrónico')
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CLIENTE)

    objects = AccountManager()
    REQUIRED_FIELDS = ['email']

    class Meta:
        constraints = [
            models.UniqueConstraint(Lower('email'), name='accounts_user_email_ci_unique'),
        ]


class SecurityEvent(models.Model):
    class Kind(models.TextChoices):
        REGISTER = 'REGISTER', 'Registro'
        LOGIN = 'LOGIN', 'Inicio de sesión'
        LOGIN_FAILED = 'LOGIN_FAILED', 'Inicio de sesión fallido'
        LOGOUT = 'LOGOUT', 'Cierre de sesión'
        PASSWORD_RESET_REQUEST = 'PASSWORD_RESET_REQUEST', 'Solicitud de recuperación'
        PASSWORD_RESET_COMPLETE = 'PASSWORD_RESET_COMPLETE', 'Contraseña restablecida'
        PROFILE_UPDATED = 'PROFILE_UPDATED', 'Perfil actualizado'
        ORDER_CREATED = 'ORDER_CREATED', 'Orden creada'
        PAYMENT_SUCCEEDED = 'PAYMENT_SUCCEEDED', 'Pago simulado exitoso'
        PAYMENT_FAILED = 'PAYMENT_FAILED', 'Pago simulado fallido'
        ORDER_ACCESS_DENIED = 'ORDER_ACCESS_DENIED', 'Acceso a orden denegado'
        ORDER_CONFLICT = 'ORDER_CONFLICT', 'Conflicto de orden'
        RECEIPT_ISSUED = 'RECEIPT_ISSUED', 'Comprobante emitido'
        RECEIPT_VERIFIED = 'RECEIPT_VERIFIED', 'Comprobante verificado'
        RECEIPT_INVALID = 'RECEIPT_INVALID', 'Comprobante inválido'
        RECEIPT_ACCESS_DENIED = 'RECEIPT_ACCESS_DENIED', 'Acceso a comprobante denegado'
        RECEIPT_ERROR = 'RECEIPT_ERROR', 'Error al emitir comprobante'
        DOWNLOAD_CREATED = 'DOWNLOAD_CREATED', 'Descarga personalizada emitida'
        DOWNLOAD_DENIED = 'DOWNLOAD_DENIED', 'Descarga denegada'
        DOWNLOAD_ERROR = 'DOWNLOAD_ERROR', 'Error de descarga'
        FINGERPRINT_EXTRACTED = 'FINGERPRINT_EXTRACTED', 'Huella extraída'
        FINGERPRINT_INVALID = 'FINGERPRINT_INVALID', 'Huella inválida'
        FINGERPRINT_ACCESS_DENIED = 'FINGERPRINT_ACCESS_DENIED', 'Acceso a huellas denegado'

    kind = models.CharField(max_length=32, choices=Kind.choices)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='security_events',
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
