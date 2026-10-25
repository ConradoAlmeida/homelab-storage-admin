from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="backup_index"),
    path("disks/setup/", views.disk_wizard, name="backup_disk_wizard"),
    path("credentials/", views.credentials, name="backup_credentials"),
    path("jobs/new/", views.job_form, name="backup_job_new"),
    path("jobs/<str:name>/edit/", views.job_form, name="backup_job_edit"),
    path("jobs/<str:name>/run/", views.job_run, name="backup_job_run"),
    path("jobs/<str:name>/toggle/", views.job_toggle, name="backup_job_toggle"),
    path("jobs/<str:name>/delete/", views.job_delete, name="backup_job_delete"),
]
