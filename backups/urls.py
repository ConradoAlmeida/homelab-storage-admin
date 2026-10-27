from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="backup_index"),
    path("snapshots/", views.snapshots, name="backup_snapshots"),
    path(
        "snapshots/<str:snapshot_id>/browse/",
        views.snapshot_browse,
        name="backup_snapshot_browse",
    ),
    path(
        "snapshots/<str:snapshot_id>/download/",
        views.snapshot_download,
        name="backup_snapshot_download",
    ),
    path("disks/setup/", views.disk_wizard, name="backup_disk_wizard"),
    path("credentials/", views.credentials, name="backup_credentials"),
    path("cold/", views.cold_index, name="cold_index"),
    path("cold/setup/", views.cold_prepare, name="cold_prepare"),
    path("cold/copy/", views.cold_copy, name="cold_copy"),
    path("cold/eject/", views.cold_eject, name="cold_eject"),
    path("jobs/new/", views.job_form, name="backup_job_new"),
    path("jobs/<str:name>/edit/", views.job_form, name="backup_job_edit"),
    path("jobs/<str:name>/run/", views.job_run, name="backup_job_run"),
    path("jobs/<str:name>/toggle/", views.job_toggle, name="backup_job_toggle"),
    path("jobs/<str:name>/delete/", views.job_delete, name="backup_job_delete"),
]
