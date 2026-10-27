from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="storage_index"),
    path("refresh/", views.refresh, name="storage_refresh"),
    path("smart/", views.smart, name="storage_smart"),
    path("smart/test/", views.smart_test, name="storage_smart_test"),
]
