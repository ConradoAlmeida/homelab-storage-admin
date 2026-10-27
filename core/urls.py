from django.conf import settings
from django.urls import path

from . import views

CREDENCIAIS_ATIVA = bool(settings.CREDENTIALS_URL and settings.CREDENTIALS_API_TOKEN)

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
    path("metrics/network/", views.NetworkMetricsView.as_view(), name="network_metrics"),
    path("metrics/live/", views.LiveMetricsView.as_view(), name="live_metrics"),
    path("metrics/shares/", views.ShareSizesView.as_view(), name="share_sizes"),
    path("usuarios/", views.UsersView.as_view(), name="users"),
    path("shares/", views.SharesView.as_view(), name="shares"),
    path("shares/novo/", views.ShareCreateView.as_view(), name="share_create"),
    path("snapshots/", views.SnapshotsView.as_view(), name="snapshots"),
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
]

if not CREDENCIAIS_ATIVA:
    urlpatterns += [
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
    ]
