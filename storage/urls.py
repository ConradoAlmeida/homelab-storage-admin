from django.urls import path

from . import views

urlpatterns = [
    path("", views.StorageIndexView.as_view(), name="storage_index"),
    path("refresh/", views.StorageRefreshView.as_view(), name="storage_refresh"),
    path("smart/", views.StorageSmartView.as_view(), name="storage_smart"),
    path(
        "smart/test/",
        views.StorageSmartTestView.as_view(),
        name="storage_smart_test",
    ),
]
