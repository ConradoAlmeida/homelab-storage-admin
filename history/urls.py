from django.urls import path

from . import views

urlpatterns = [
    path("", views.HistoryIndexView.as_view(), name="history_index"),
    path("<str:share>/", views.ShareDetailView.as_view(), name="history_share"),
    path(
        "<str:share>/<str:snapshot>/download/<path:filepath>",
        views.HistoryDownloadView.as_view(),
        name="history_download",
    ),
    path(
        "<str:share>/versions/<path:filepath>",
        views.HistoryVersionsView.as_view(),
        name="history_versions",
    ),
    path(
        "<str:share>/<str:snapshot>/<path:filepath>",
        views.HistoryBrowseView.as_view(),
        name="history_browse",
    ),
    path(
        "<str:share>/<str:snapshot>/",
        views.HistoryBrowseView.as_view(),
        name="history_browse_root",
    ),
]
