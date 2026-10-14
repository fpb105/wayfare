from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Intrests, Profile


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
        profile.home = "china"
        profile.currency = "YEN"
        profile.type = Profile.UserPreference.BUDGET
        profile.intrests.add(Intrests.objects.create(intrests="food"))
        profile.save()

        profile.refresh_from_db()
        self.assertEqual(profile.home, "china")
        self.assertEqual(profile.currency, "YEN")
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
