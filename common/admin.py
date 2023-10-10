from django.contrib import admin

# Register your models here.


from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DefaultUserAdmin
from django.contrib.auth.models import User
from .models import UserProfile

class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'Profile'
    fk_name = 'user'


class UserAdmin(DefaultUserAdmin):
    inlines = (UserProfileInline, )
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'get_affiliation')
    list_select_related = ('userprofile', )

    def get_affiliation(self, instance):
        return instance.userprofile.affiliation
    get_affiliation.short_description = 'Affiliation'

admin.site.unregister(User)
admin.site.register(User, UserAdmin)

