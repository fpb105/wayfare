import json
import re
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Airport, City, Intrests, Profile
from . import views as wayfare_views

TEST_CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
    "chat": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
}


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


class ChatParsingAndLoopTests(TestCase):
    def test_parse_reply_accepts_strict_hidden_true(self):
        hidden, apis = wayfare_views._chat_parse_reply('[true, [["city_detail", {"name": "Narnia"}]]]')
        self.assertTrue(hidden)
        self.assertEqual(apis, [["city_detail", {"name": "Narnia"}]])

    def test_parse_reply_accepts_strict_hidden_false(self):
        hidden, apis = wayfare_views._chat_parse_reply("[false, []]")
        self.assertFalse(hidden)
        self.assertEqual(apis, [])

    def test_parse_reply_rejects_invalid_json(self):
        with self.assertRaises(ValueError):
            wayfare_views._chat_parse_reply("")

    def test_parse_reply_rejects_wrong_shape(self):
        with self.assertRaises(ValueError):
            wayfare_views._chat_parse_reply('[true, [], "extra"]')

    def test_parse_reply_rejects_non_bool_hidden(self):
        with self.assertRaises(ValueError):
            wayfare_views._chat_parse_reply('["true", []]')

    @patch("wayfare.views._chat_ask_ollama")
    def test_run_chat_loop_calls_apis_then_returns_plain_answer(self, mock_ask):
        mock_ask.side_effect = [
            '[true, [["user_preferences", {}]]]',
            "[false, []]",
            "Here is your answer.",
        ]
        chat_messages = [{"role": "system", "content": "system prompt"}]
        user = get_user_model().objects.create_user(
            username="loopuser", email="loop@example.com", password="test-password"
        )

        reply = wayfare_views._run_chat_loop(chat_messages, user)

        self.assertEqual(reply, "Here is your answer.")
        self.assertEqual(mock_ask.call_count, 3)
        roles = [m["role"] for m in chat_messages]
        self.assertIn("assistant", roles)

    @patch("wayfare.views._chat_ask_ollama")
    @patch("wayfare.views.CHAT_MAX_HIDDEN_STEPS", 2)
    def test_run_chat_loop_gives_up_after_max_steps(self, mock_ask):
        mock_ask.return_value = "[true, []]"
        user = get_user_model().objects.create_user(
            username="stuckuser", email="stuck@example.com", password="test-password"
        )

        with self.assertRaises(RuntimeError):
            wayfare_views._run_chat_loop([{"role": "system", "content": "system prompt"}], user)


@override_settings(CACHES=TEST_CACHES)
class ChatCacheTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="chatter", email="chatter@example.com", password="test-password"
        )
        self.client.login(email="chatter@example.com", password="test-password")

    def _extract_chat_id(self, content):
        match = re.search(r'name="chat_id" value="([0-9a-f]+)"', content.decode())
        self.assertIsNotNone(match, "chat_id hidden field not found in response")
        return match.group(1)

    def test_chat_page_issues_a_fresh_chat_id_every_load(self):
        first = self._extract_chat_id(self.client.get(reverse("chat")).content)
        second = self._extract_chat_id(self.client.get(reverse("chat")).content)
        self.assertNotEqual(first, second)

    def test_chat_send_stores_messages_in_the_chat_cache(self):
        chat_id = self._extract_chat_id(self.client.get(reverse("chat")).content)

        response = self.client.post(reverse("chat_send"), {"chat_id": chat_id, "message": "hi there"})

        self.assertEqual(response.status_code, 200)
        chat_cache = wayfare_views.caches["chat"]
        stored_messages = chat_cache.get(f"chat_messages_{chat_id}")
        self.assertEqual(stored_messages[0]["role"], "system")
        self.assertEqual(stored_messages[-1], {"role": "user", "content": "hi there"})
        stored_visible = chat_cache.get(f"chat_visible_{chat_id}")
        self.assertEqual(stored_visible, [{"role": "user", "content": "hi there"}])

    def test_chat_send_rejects_a_second_message_while_locked(self):
        chat_id = self._extract_chat_id(self.client.get(reverse("chat")).content)
        wayfare_views.caches["chat"].set(f"chat_lock_{chat_id}", True, timeout=120)

        response = self.client.post(reverse("chat_send"), {"chat_id": chat_id, "message": "hi there"})

        self.assertEqual(response.status_code, 400)

    def test_chat_reply_without_chat_id_returns_400(self):
        response = self.client.get(reverse("chat_reply"))
        self.assertEqual(response.status_code, 400)

    @patch("wayfare.views._chat_ask_ollama")
    def test_chat_reply_appends_answer_and_releases_lock(self, mock_ask):
        mock_ask.side_effect = ["[false, []]", "Final answer."]
        chat_id = self._extract_chat_id(self.client.get(reverse("chat")).content)
        self.client.post(reverse("chat_send"), {"chat_id": chat_id, "message": "hi there"})

        response = self.client.get(reverse("chat_reply"), {"chat_id": chat_id})

        self.assertEqual(response.status_code, 200)
        self.assertIn("Final answer.", response.content.decode())

        chat_cache = wayfare_views.caches["chat"]
        self.assertIsNone(chat_cache.get(f"chat_lock_{chat_id}"))
        visible = chat_cache.get(f"chat_visible_{chat_id}")
        self.assertEqual(visible[-1], {"role": "assistant", "content": "Final answer."})

    def test_chat_views_require_login(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("chat")).status_code, 302)
        self.assertEqual(self.client.post(reverse("chat_send"), {"message": "hi"}).status_code, 302)
        self.assertEqual(self.client.get(reverse("chat_reply"), {"chat_id": "x"}).status_code, 302)
