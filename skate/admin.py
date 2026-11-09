from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User, Spots, Rating


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('username', 'email', 'created_at', 'is_staff')
    ordering = ('-created_at',)
    readonly_fields = ('created_at',)
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Personal info', {'fields': ('email',)}),
        ('Permissions', {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
        }),
        ('Important dates', {'fields': ('last_login', 'date_joined', 'created_at')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'email', 'password1', 'password2'),
        }),
    )


@admin.register(Spots)
class SpotsAdmin(admin.ModelAdmin):
    list_display = ('name_spot', 'user', 'created_at')
    search_fields = ('name_spot',)
    readonly_fields = ('created_at',)


@admin.register(Rating)
class RatingAdmin(admin.ModelAdmin):
    list_display = ('user', 'spot', 'score', 'created_at')
    readonly_fields = ('created_at',)
