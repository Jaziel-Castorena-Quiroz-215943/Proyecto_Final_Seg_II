import logging

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST, require_http_methods

from accounts.models import SecurityEvent, User
from orders.access import retry_on_sqlite_lock, roles_required

from .fingerprinting import (
    MAX_MARKED_PDF_SIZE,
    FingerprintAccessError,
    FingerprintError,
    identify_download,
    issue_download,
)
from .forms import FingerprintExtractionForm

logger = logging.getLogger(__name__)


@roles_required(User.Role.CLIENTE, denied_kind=SecurityEvent.Kind.DOWNLOAD_DENIED)
@retry_on_sqlite_lock
@never_cache
@require_POST
def download(request, pk):
    try:
        data = issue_download(request.user, pk)
    except FingerprintAccessError:
        SecurityEvent.objects.create(kind=SecurityEvent.Kind.DOWNLOAD_DENIED, user=request.user)
        raise Http404
    except FingerprintError as exc:
        logger.warning('No se pudo generar el PDF personalizado: %s', exc)
        SecurityEvent.objects.create(kind=SecurityEvent.Kind.DOWNLOAD_ERROR, user=request.user)
        return HttpResponse('No se puede generar el PDF de esta orden.', status=409)
    response = HttpResponse(data, content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="producto-personalizado.pdf"'
    response['X-Content-Type-Options'] = 'nosniff'
    response['Content-Security-Policy'] = 'sandbox'
    return response


@login_required
@never_cache
@require_http_methods(['GET', 'POST'])
def extract(request):
    if not request.user.is_active or not request.user.is_superuser:
        SecurityEvent.objects.create(kind=SecurityEvent.Kind.FINGERPRINT_ACCESS_DENIED, user=request.user)
        raise PermissionDenied
    form = FingerprintExtractionForm(
        request.POST if request.method == 'POST' else None,
        request.FILES if request.method == 'POST' else None,
    )
    if request.method == 'POST' and not form.is_valid():
        SecurityEvent.objects.create(kind=SecurityEvent.Kind.FINGERPRINT_INVALID, user=request.user)
        return render(request, 'security/extract.html', {'form': form}, status=400)
    if request.method == 'POST':
        try:
            chunks = []
            size = 0
            for chunk in form.cleaned_data['pdf'].chunks():
                size += len(chunk)
                if size > MAX_MARKED_PDF_SIZE:
                    raise FingerprintError('El archivo supera el tamaño permitido.')
                chunks.append(chunk)
            download = identify_download(b''.join(chunks))
        except FingerprintError:
            SecurityEvent.objects.create(kind=SecurityEvent.Kind.FINGERPRINT_INVALID, user=request.user)
            return HttpResponse('No se puede identificar el documento.', status=400)
        SecurityEvent.objects.create(kind=SecurityEvent.Kind.FINGERPRINT_EXTRACTED, user=request.user)
        return render(request, 'security/extract.html', {'form': form, 'download': download})
    return render(request, 'security/extract.html', {'form': form})
