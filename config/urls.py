from django.conf import settings
from django.urls import include, path

urlpatterns =[]

if settings.ADMIN_ENABLED is True:
    from django.contrib import admin
    urlpatterns += [path('admin/', admin.site.urls),]

urlpatterns += [
    path("accounts/", include("allauth.urls")),
    path("", include("wayfare.urls")),
]