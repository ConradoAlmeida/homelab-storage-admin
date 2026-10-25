from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="backup_index"),
    path("disks/setup/", views.disk_wizard, name="backup_disk_wizard"),
    path("credentials/", views.credentials, name="backup_credentials"),
]
