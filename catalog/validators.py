import hashlib
from pathlib import Path

import pymupdf
from django.core.exceptions import ValidationError


MAX_PDF_SIZE = 20 * 1024 * 1024


def inspect_pdf(upload):
    if Path(upload.name).suffix.lower() != '.pdf':
        raise ValidationError('El archivo debe tener extensión .pdf.')
    if upload.size > MAX_PDF_SIZE:
        raise ValidationError('El archivo no puede superar 20 MiB.')

    digest = hashlib.sha256()
    chunks = []
    size = 0
    try:
        upload.seek(0)
        for chunk in upload.chunks():
            size += len(chunk)
            if size > MAX_PDF_SIZE:
                raise ValidationError('El archivo no puede superar 20 MiB.')
            digest.update(chunk)
            chunks.append(chunk)
        data = b''.join(chunks)
        if not data.startswith(b'%PDF-'):
            raise ValidationError('El archivo no tiene una cabecera PDF válida.')
        try:
            with pymupdf.open(stream=data, filetype='pdf') as document:
                if (
                    not document.is_pdf or document.is_encrypted or document.needs_pass
                    or (document.metadata and document.metadata.get('encryption'))
                ):
                    raise ValidationError('El PDF no puede estar cifrado.')
                if document.is_repaired or document.page_count == 0:
                    raise ValidationError('El PDF está dañado o no contiene páginas.')
        except pymupdf.FileDataError as exc:
            raise ValidationError('El archivo PDF no es válido.') from exc
        return digest.hexdigest()
    finally:
        upload.seek(0)
