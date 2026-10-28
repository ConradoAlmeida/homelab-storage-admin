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
        "disks/check/",
        views.BackupCheckView.as_view(),
        name="backup_check",
    ),
    path(
        "gitea/",
        views.GiteaBackupView.as_view(),
        name="gitea_backup",
    ),
    path(
        "gitea/start/",
        views.GiteaBackupStartView.as_view(),
        name="gitea_backup_start",
    ),
    path(
        "gitea/status/",
        views.GiteaBackupStatusView.as_view(),
        name="gitea_backup_status",
    ),
    path(
        "arquivos/",
        views.ArquivosJobsView.as_view(),
        name="arquivos_backup_index",
    ),
    path(
        "arquivos/new/",
        views.ArquivosJobFormView.as_view(),
        name="arquivos_job_new",
    ),
    path(
        "arquivos/<str:job>/",
        views.ArquivosJobView.as_view(),
        name="arquivos_job",
    ),
    path(
        "arquivos/<str:job>/edit/",
        views.ArquivosJobFormView.as_view(),
        name="arquivos_job_edit",
    ),
    path(
        "arquivos/<str:job>/run/",
        views.ArquivosJobRunView.as_view(),
        name="arquivos_job_run",
    ),
    path(
        "arquivos/<str:job>/delete/",
        views.ArquivosJobDeleteView.as_view(),
        name="arquivos_job_delete",
    ),
    path(
        "arquivos/<str:job>/<str:archive>/verify/",
        views.ArquivosJobVerifyView.as_view(),
        name="arquivos_job_verify",
    ),
    path(
        "arquivos/<str:job>/<str:archive>/download/",
        views.ArquivosJobDownloadView.as_view(),
        name="arquivos_job_download",
    ),
    path(
        "arquivos/<str:job>/<str:archive>/restore/",
        views.ArquivosJobRestoreView.as_view(),
        name="arquivos_job_restore",
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
