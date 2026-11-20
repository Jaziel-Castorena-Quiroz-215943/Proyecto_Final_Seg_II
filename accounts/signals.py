from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver

from .models import SecurityEvent


@receiver(user_logged_in)
def record_login(sender, request, user, **kwargs):
    SecurityEvent.objects.create(kind=SecurityEvent.Kind.LOGIN, user=user)


@receiver(user_logged_out)
def record_logout(sender, request, user, **kwargs):
    if user is not None:
        SecurityEvent.objects.create(kind=SecurityEvent.Kind.LOGOUT, user=user)


@receiver(user_login_failed)
def record_failed_login(sender, credentials, request, **kwargs):
    SecurityEvent.objects.create(kind=SecurityEvent.Kind.LOGIN_FAILED)
