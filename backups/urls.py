from django.urls import path

from . import views

urlpatterns = [
    path("", views.BackupIndexView.as_view(), name="backup_index"),
    path(
        "snapshots/",
        views.BackupSnapshotsView.as_view(),
        name="backup_snapshots",
    ),
    path(
        "snapshots/<str:snapshot_id>/browse/",
        views.ResticSnapshotBrowseView.as_view(),
        name="backup_snapshot_browse",
    ),
    path(
        "snapshots/<str:snapshot_id>/download/",
        views.ResticSnapshotDownloadView.as_view(),
        name="backup_snapshot_download",
    ),
    path(
        "disks/setup/",
        views.DiskWizardView.as_view(),
        name="backup_disk_wizard",
    ),
    path(
        "credentials/",
        views.CredentialsView.as_view(),
        name="backup_credentials",
    ),
    path(
        "credenciais-app/",
        views.CredenciaisBackupView.as_view(),
        name="credenciais_backup_index",
    ),
    path(
        "credenciais-app/run/",
        views.CredenciaisBackupRunView.as_view(),
        name="credenciais_backup_run",
    ),
    path(
        "credenciais-app/files/add/",
        views.CredenciaisBackupFileAddView.as_view(),
        name="credenciais_backup_file_add",
    ),
    path(
        "credenciais-app/files/remove/",
        views.CredenciaisBackupFileRemoveView.as_view(),
        name="credenciais_backup_file_remove",
    ),
    path(
        "credenciais-app/<str:archive>/verify/",
        views.CredenciaisBackupVerifyView.as_view(),
        name="credenciais_backup_verify",
    ),
    path(
        "credenciais-app/<str:archive>/download/",
        views.CredenciaisBackupDownloadView.as_view(),
        name="credenciais_backup_download",
    ),
    path(
        "credenciais-app/<str:archive>/restore/",
        views.CredenciaisBackupRestoreView.as_view(),
        name="credenciais_backup_restore",
    ),
    path("cold/", views.ColdIndexView.as_view(), name="cold_index"),
    path("cold/setup/", views.ColdPrepareView.as_view(), name="cold_prepare"),
    path("cold/copy/", views.ColdCopyView.as_view(), name="cold_copy"),
    path("cold/eject/", views.ColdEjectView.as_view(), name="cold_eject"),
    path("jobs/new/", views.JobFormView.as_view(), name="backup_job_new"),
    path(
        "jobs/<str:name>/edit/",
        views.JobFormView.as_view(),
        name="backup_job_edit",
    ),
    path("jobs/<str:name>/run/", views.JobRunView.as_view(), name="backup_job_run"),
    path(
        "jobs/<str:name>/toggle/",
        views.JobToggleView.as_view(),
        name="backup_job_toggle",
    ),
    path(
        "jobs/<str:name>/delete/",
        views.JobDeleteView.as_view(),
        name="backup_job_delete",
    ),
]
