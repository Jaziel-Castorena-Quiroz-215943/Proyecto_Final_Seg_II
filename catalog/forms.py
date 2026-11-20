from django import forms
from django.core.files.uploadedfile import UploadedFile

from .models import Product
from .validators import inspect_pdf


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ('name', 'description', 'price', 'status', 'pdf')
        widgets = {'pdf': forms.FileInput(attrs={'accept': '.pdf,application/pdf'})}

    def clean_pdf(self):
        pdf = self.cleaned_data['pdf']
        if isinstance(pdf, UploadedFile):
            inspect_pdf(pdf)
        return pdf
