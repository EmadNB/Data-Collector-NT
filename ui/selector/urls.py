from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("api/selection/", views.selection_api, name="selection_api"),
    path("api/generate/", views.generate, name="generate"),
]
