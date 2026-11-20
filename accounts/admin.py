from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .forms import RegistrationForm
from .models import SecurityEvent, User


@admin.register(User)
class AccountAdmin(UserAdmin):
    add_form = RegistrationForm
    fieldsets = UserAdmin.fieldsets + (('Rol', {'fields': ('role',)}),)
    add_fieldsets = (
        (None, {'classes': ('wide',), 'fields': ('username', 'email', 'role', 'password1', 'password2')}),
    )
    list_display = ('username', 'email', 'role', 'is_staff', 'is_active')

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(SecurityEvent)
class SecurityEventAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'kind', 'user')
    list_filter = ('kind',)
    readonly_fields = ('created_at', 'kind', 'user')

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
