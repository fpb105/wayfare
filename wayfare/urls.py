from django.urls import path

from . import views

urlpatterns = [
    path("make_profile", views.edit_profile, name="edit_profile"),
    path("profile", views.profile, name="profile"),
    path("api/airports/search", views.airport_search, name="airport_search"),
    path("search", views.flight_search, name="search"),
    path("results", views.flight_results, name="results"),
]