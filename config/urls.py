from django.conf import settings
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

admin.site.site_header = settings.SITE_NAME
admin.site.site_title = settings.SITE_NAME
admin.site.index_title = f"Administração do {settings.SITE_NAME}"
admin.site.site_url = "/"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("login/", auth_views.LoginView.as_view(template_name="login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("history/", include("history.urls")),
    path("storage/", include("storage.urls")),
    path("backups/", include("backups.urls")),
    path("", include("core.urls")),
]
