from django.urls import path

from . import downloads, system_views, views

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
    path("saude/", views.HealthView.as_view(), name="health_index"),
    path("rede/", views.NetworkView.as_view(), name="network_index"),
    path("sistema/", system_views.SystemHostView.as_view(), name="system_host"),
    path(
        "sistema/config/",
        system_views.SystemConfigView.as_view(),
        name="system_config",
    ),
    path("sistema/chaves/", system_views.SystemKeysView.as_view(), name="system_keys"),
    path("sistema/logs/", system_views.SystemLogsView.as_view(), name="system_logs"),
    path(
        "sistema/servicos/",
        system_views.SystemServicesView.as_view(),
        name="system_services",
    ),
    path(
        "sistema/servicos/acao/",
        system_views.SystemServiceActionView.as_view(),
        name="system_service_action",
    ),
    path(
        "sistema/terminal/",
        system_views.TerminalPageView.as_view(),
        name="system_terminal",
    ),
    path(
        "sistema/terminal/io/",
        system_views.TerminalIoView.as_view(),
        name="system_terminal_io",
    ),
    path(
        "rede/firewall/",
        views.FirewallActionView.as_view(),
        name="firewall_action",
    ),
    path("containers/", views.ContainersView.as_view(), name="containers"),
    path(
        "containers/acao/",
        views.ContainerActionView.as_view(),
        name="container_action",
    ),
    path(
        "containers/logs/",
        views.ContainerLogsView.as_view(),
        name="container_logs",
    ),
    path("metrics/network/", views.NetworkMetricsView.as_view(), name="network_metrics"),
    path("metrics/live/", views.LiveMetricsView.as_view(), name="live_metrics"),
    path("metrics/shares/", views.ShareSizesView.as_view(), name="share_sizes"),
    path("usuarios/", views.UsersView.as_view(), name="users"),
    path("usuarios/novo/", views.UserCreateView.as_view(), name="user_create"),
    path(
        "usuarios/grupos/novo/",
        views.GroupCreateView.as_view(),
        name="group_create",
    ),
    path("usuarios/senha/", views.UserPasswordView.as_view(), name="user_password"),
    path("usuarios/grupos/", views.UserGroupsView.as_view(), name="user_groups"),
    path("usuarios/toggle/", views.UserToggleView.as_view(), name="user_toggle"),
    path("usuarios/excluir/", views.UserDeleteView.as_view(), name="user_delete"),
    path(
        "usuarios/grupos/excluir/",
        views.GroupDeleteView.as_view(),
        name="group_delete",
    ),
    path("shares/", views.SharesView.as_view(), name="shares"),
    path("shares/novo/", views.ShareCreateView.as_view(), name="share_create"),
    path("torrents/", downloads.TorrentsView.as_view(), name="torrents"),
    path("torrents/estado/", downloads.TorrentStatusView.as_view(), name="torrent_status"),
    path("torrents/adicionar/", downloads.TorrentAddView.as_view(), name="torrent_add"),
    path("torrents/acao/", downloads.TorrentActionView.as_view(), name="torrent_action"),
    path(
        "torrents/organizar/listar/",
        downloads.TorrentOrganizeListView.as_view(),
        name="torrent_organize_list",
    ),
    path(
        "torrents/organizar/",
        downloads.TorrentOrganizeApplyView.as_view(),
        name="torrent_organize",
    ),
    path("api/torrents/", downloads.TorrentEnvioApiView.as_view(), name="torrent_api_add"),
    path(
        "api/torrents/bibliotecas/",
        downloads.TorrentBibliotecasApiView.as_view(),
        name="torrent_api_libraries",
    ),
    path("tarefas/<str:task_id>/", views.TaskStatusView.as_view(), name="task_status"),
    path("snapshots/", views.SnapshotsView.as_view(), name="snapshots"),
    path(
        "snapshots/politica/nova/",
        views.SnapshotPolicyView.as_view(),
        name="snapshot_policy_new",
    ),
    path(
        "snapshots/<str:share>/politica/",
        views.SnapshotPolicyView.as_view(),
        name="snapshot_policy_edit",
    ),
    path(
        "snapshots/criar/",
        views.SnapshotCreateView.as_view(),
        name="snapshot_create",
    ),
    path(
        "snapshots/remover/",
        views.SnapshotDeleteView.as_view(),
        name="snapshot_delete",
    ),
    path(
        "snapshots/restaurar/",
        views.SnapshotRestoreView.as_view(),
        name="snapshot_restore",
    ),
]
