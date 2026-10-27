from django.urls import path
from django.views.generic import TemplateView

from core.auth import login_view

urlpatterns = [
    path("login/", login_view, name="login"),
    path("logout/", TemplateView.as_view(template_name="login.html"), name="logout"),
    path("", TemplateView.as_view(template_name="login.html"), name="dashboard"),
    path("usuarios/", TemplateView.as_view(template_name="login.html"), name="users"),
    path("shares/", TemplateView.as_view(template_name="login.html"), name="shares"),
    path("snapshots/", TemplateView.as_view(template_name="login.html"), name="snapshots"),
    path("history/", TemplateView.as_view(template_name="login.html"), name="history_index"),
    path("storage/", TemplateView.as_view(template_name="login.html"), name="storage_index"),
    path("backups/", TemplateView.as_view(template_name="login.html"), name="backup_index"),
]
