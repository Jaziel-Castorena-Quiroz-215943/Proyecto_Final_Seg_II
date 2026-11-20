from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_http_methods

from .forms import ProfileForm, RegistrationForm
from .models import SecurityEvent


@require_http_methods(['GET', 'POST'])
def register(request):
    form = RegistrationForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            user = form.save()
            SecurityEvent.objects.create(kind=SecurityEvent.Kind.REGISTER, user=user)
        messages.success(request, 'Cuenta creada. Ya puedes iniciar sesión.')
        return redirect('accounts:login')
    return render(request, 'accounts/form.html', {'form': form, 'title': 'Registro'})


@login_required
@require_http_methods(['GET', 'POST'])
def profile(request):
    form = ProfileForm(request.POST if request.method == 'POST' else None, instance=request.user)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            form.save()
            SecurityEvent.objects.create(kind=SecurityEvent.Kind.PROFILE_UPDATED, user=request.user)
        messages.success(request, 'Perfil actualizado.')
        return redirect('accounts:profile')
    return render(request, 'accounts/profile.html', {'form': form})


class PasswordResetView(auth_views.PasswordResetView):
    template_name = 'accounts/form.html'
    email_template_name = 'accounts/password_reset_email.txt'
    subject_template_name = 'accounts/password_reset_subject.txt'
    success_url = reverse_lazy('accounts:password_reset_done')
    extra_context = {'title': 'Recuperar contraseña'}

    def form_valid(self, form):
        SecurityEvent.objects.create(kind=SecurityEvent.Kind.PASSWORD_RESET_REQUEST)
        return super().form_valid(form)


class PasswordResetConfirmView(auth_views.PasswordResetConfirmView):
    template_name = 'accounts/password_reset_confirm.html'
    success_url = reverse_lazy('accounts:password_reset_complete')

    def form_valid(self, form):
        with transaction.atomic():
            response = super().form_valid(form)
            SecurityEvent.objects.create(kind=SecurityEvent.Kind.PASSWORD_RESET_COMPLETE, user=self.user)
        return response
