from django import forms


class VerifyReceiptForm(forms.Form):
    document = forms.CharField(
        label='Comprobante JSON', max_length=1000000, widget=forms.Textarea,
    )
