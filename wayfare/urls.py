from django.urls import path

from . import views

urlpatterns = [
    path("make_profile", views.edit_profile, name="edit_profile"),
    path("profile", views.profile, name="profile"),
    path("api/airports/search", views.airport_search, name="airport_search"),
    path("api/user-preferences", views.user_preferences, name="user_preferences"),
    path("api/user-intrests", views.user_intrests, name="user_intrests"),
    path("api/cities/detail", views.city_detail, name="city_detail"),
    path("api/cities/search", views.city_search, name="city_search"),
    path("api/cities/<int:city_id>/airports", views.city_airports, name="city_airports"),
    path("search", views.flight_search, name="search"),
    path("results", views.flight_results, name="results"),
]