from django import forms

from .models import SimulatedPayment


class CheckoutForm(forms.Form):
    key = forms.UUIDField()
    quote = forms.CharField(max_length=1000000)


class PaymentForm(forms.Form):
    result = forms.ChoiceField(choices=SimulatedPayment.Result.choices)
