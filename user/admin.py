from django.contrib import admin
from .models import UserInfo


class UserInfoAdmin(admin.ModelAdmin):
    list_display = ('username', 'uemail', 'uaddress', 'uyoubian', 'uphone', 'create_time')
    search_fields = ('username', 'uemail')
    ordering = ('-create_time',)


admin.site.register(UserInfo, UserInfoAdmin)

