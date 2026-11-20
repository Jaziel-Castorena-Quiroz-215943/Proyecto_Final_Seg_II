from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import User


class EmailValidationMixin:
    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        users = User.objects.filter(email__iexact=email)
        if self.instance.pk:
            users = users.exclude(pk=self.instance.pk)
        if users.exists():
            raise forms.ValidationError('Este correo ya está registrado.')
        return email


class RegistrationForm(EmailValidationMixin, UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'email')


class ProfileForm(EmailValidationMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'email')
