import sqlite3
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import OperationalError
from django.http import HttpResponse

from accounts.models import SecurityEvent, User


def roles_required(*roles, denied_kind=SecurityEvent.Kind.ORDER_ACCESS_DENIED):
    def decorate(view):
        @login_required
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if not request.user.is_active or request.user.role not in roles:
                SecurityEvent.objects.create(kind=denied_kind, user=request.user)
                raise PermissionDenied
            return view(request, *args, **kwargs)
        return wrapped
    return decorate


def retry_on_sqlite_lock(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        try:
            return view(request, *args, **kwargs)
        except OperationalError as exc:
            code = getattr(exc.__cause__, 'sqlite_errorcode', 0) & 0xff
            if code not in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
                raise
            response = HttpResponse('La operación está ocupada. Inténtalo de nuevo.', status=503)
            response['Retry-After'] = '1'
            return response
    return wrapped
