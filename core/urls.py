from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("metrics/network/", views.network_metrics, name="network_metrics"),
    path("metrics/shares/", views.share_sizes, name="share_sizes"),
    path("tarefas/", views.tasks, name="tasks"),
    path("tarefas/nova/", views.task_create, name="task_create"),
    path("tarefas/<str:task_id>/", views.task_detail, name="task_detail"),
    path("tarefas/<str:task_id>/cancelar/", views.task_cancel, name="task_cancel"),
    path("usuarios/", views.users, name="users"),
    path("usuarios/novo/", views.user_create, name="user_create"),
    path("usuarios/grupos/novo/", views.group_create, name="group_create"),
    path("usuarios/senha/", views.user_password, name="user_password"),
    path("usuarios/grupos/", views.user_groups, name="user_groups"),
    path("usuarios/toggle/", views.user_toggle, name="user_toggle"),
    path("shares/", views.shares, name="shares"),
    path("shares/novo/", views.share_create, name="share_create"),
    path("snapshots/", views.snapshots, name="snapshots"),
    path("snapshots/criar/", views.snapshot_create, name="snapshot_create"),
    path("snapshots/remover/", views.snapshot_delete, name="snapshot_delete"),
]
