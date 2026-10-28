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
        "arquivos/",
        views.ArquivosBackupView.as_view(),
        name="arquivos_backup_index",
    ),
    path(
        "arquivos/run/",
        views.ArquivosBackupRunView.as_view(),
        name="arquivos_backup_run",
    ),
    path(
        "arquivos/settings/",
        views.ArquivosBackupSettingsView.as_view(),
        name="arquivos_backup_settings",
    ),
    path(
        "arquivos/files/add/",
        views.ArquivosBackupFileAddView.as_view(),
        name="arquivos_backup_file_add",
    ),
    path(
        "arquivos/files/remove/",
        views.ArquivosBackupFileRemoveView.as_view(),
        name="arquivos_backup_file_remove",
    ),
    path(
        "arquivos/<str:archive>/verify/",
        views.ArquivosBackupVerifyView.as_view(),
        name="arquivos_backup_verify",
    ),
    path(
        "arquivos/<str:archive>/download/",
        views.ArquivosBackupDownloadView.as_view(),
        name="arquivos_backup_download",
    ),
    path(
        "arquivos/<str:archive>/restore/",
        views.ArquivosBackupRestoreView.as_view(),
        name="arquivos_backup_restore",
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
