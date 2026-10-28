import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Airport, City, Intrests, Profile


class ProfileTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="student",
            email="student@example.com",
            password="test-password",
        )

    def test_creating_user_automatically_creates_profile(self):
        self.assertTrue(Profile.objects.filter(author=self.user).exists())

    def test_editing_profile_updates_fields(self):
        profile = self.user.profile
        profile.type = Profile.UserPreference.BUDGET
        profile.intrests.add(Intrests.objects.create(intrests="food"))
        profile.save()

        profile.refresh_from_db()
        self.assertEqual(profile.type, Profile.UserPreference.BUDGET)
        self.assertQuerySetEqual(
            profile.intrests.values_list("intrests", flat=True), ["food"]
        )

    def test_profile_view_requires_login_and_handles_missing_profile(self):
        # Logged-out users are redirected rather than erroring.
        response = self.client.get(reverse("profile"))
        self.assertEqual(response.status_code, 302)

        # Logged-in users without a profile row still get served a page
        # (the view falls back to get_or_create) instead of crashing.
        self.client.login(email="student@example.com", password="test-password")
        Profile.objects.filter(author=self.user).delete()

        response = self.client.get(reverse("profile"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Profile.objects.filter(author=self.user).exists())


class CityAndAirportApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="traveller",
            email="traveller@example.com",
            password="test-password",
        )
        self.client.login(email="traveller@example.com", password="test-password")

        self.food = Intrests.objects.create(intrests="food")
        self.nightlife = Intrests.objects.create(intrests="nightlife")

        self.barcelona = City.objects.create(name="Barcelona", budget=Profile.UserPreference.COMFORT)
        self.barcelona.known_for.add(self.food, self.nightlife)

        self.monaco = City.objects.create(name="Monaco", budget=Profile.UserPreference.LUXURY)

        self.bcn_airport = Airport.objects.create(code="BCN", name="Barcelona Airport", city=self.barcelona, flights=500)
        Airport.objects.create(code="MCM", name="Monaco Heliport", city=self.monaco, flights=10)

    def test_city_detail_finds_matching_city(self):
        response = self.client.get(reverse("city_detail"), {"name": "barcel"})
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["name"], "Barcelona")
        self.assertEqual(data["budget"], Profile.UserPreference.COMFORT)
        self.assertCountEqual(data["known_for"], ["food", "nightlife"])

    def test_city_detail_missing_city_returns_404(self):
        response = self.client.get(reverse("city_detail"), {"name": "Nowhereville"})
        self.assertEqual(response.status_code, 404)

    def test_city_detail_without_name_returns_404(self):
        response = self.client.get(reverse("city_detail"))
        self.assertEqual(response.status_code, 404)

    def test_city_search_filters_by_known_for(self):
        response = self.client.get(reverse("city_search"), {"known_for": "food"})
        data = json.loads(response.content)
        self.assertEqual([c["name"] for c in data], ["Barcelona"])

    def test_city_search_filters_by_budget(self):
        response = self.client.get(reverse("city_search"), {"budget": Profile.UserPreference.LUXURY})
        data = json.loads(response.content)
        self.assertEqual([c["name"] for c in data], ["Monaco"])

    def test_city_search_with_no_filters_returns_all(self):
        response = self.client.get(reverse("city_search"))
        data = json.loads(response.content)
        self.assertCountEqual([c["name"] for c in data], ["Barcelona", "Monaco"])

    def test_city_airports_returns_only_that_citys_airports(self):
        response = self.client.get(reverse("city_airports", args=[self.barcelona.id]))
        data = json.loads(response.content)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["code"], "BCN")

    def test_city_airports_empty_for_city_with_none(self):
        empty_city = City.objects.create(name="Nowhere")
        response = self.client.get(reverse("city_airports", args=[empty_city.id]))
        data = json.loads(response.content)
        self.assertEqual(data, [])

    def test_user_preferences_returns_this_users_saved_type(self):
        self.user.profile.type = Profile.UserPreference.LUXURY
        self.user.profile.save()

        response = self.client.get(reverse("user_preferences"))
        data = json.loads(response.content)
        self.assertEqual(data, {"type": Profile.UserPreference.LUXURY})

    def test_user_intrests_returns_this_users_saved_intrests(self):
        self.user.profile.intrests.add(self.food)

        response = self.client.get(reverse("user_intrests"))
        data = json.loads(response.content)
        self.assertEqual(data, ["food"])

    def test_api_views_require_login(self):
        self.client.logout()
        for name, args in [
            ("city_detail", []),
            ("city_search", []),
            ("city_airports", [self.barcelona.id]),
            ("user_preferences", []),
            ("user_intrests", []),
        ]:
            response = self.client.get(reverse(name, args=args))
            self.assertEqual(response.status_code, 302, f"{name} should redirect anonymous users")
