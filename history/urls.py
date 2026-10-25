from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="history_index"),
    path("<str:share>/", views.share_detail, name="history_share"),
    path(
        "<str:share>/<str:snapshot>/download/<path:filepath>",
        views.download,
        name="history_download",
    ),
    path("<str:share>/versions/<path:filepath>", views.versions, name="history_versions"),
    path(
        "<str:share>/<str:snapshot>/<path:filepath>",
        views.browse,
        name="history_browse",
    ),
    path(
        "<str:share>/<str:snapshot>/",
        views.browse,
        name="history_browse_root",
    ),
]
