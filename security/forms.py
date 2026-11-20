from django import forms

from .fingerprinting import MAX_MARKED_PDF_SIZE


class FingerprintExtractionForm(forms.Form):
    pdf = forms.FileField(label='PDF personalizado')

    def clean_pdf(self):
        uploaded = self.cleaned_data['pdf']
        if uploaded.size > MAX_MARKED_PDF_SIZE:
            raise forms.ValidationError('El archivo no puede superar 30 MiB.')
        return uploaded
