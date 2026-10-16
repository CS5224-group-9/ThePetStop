from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase


class MeViewTests(APITestCase):
    def test_returns_current_user(self):
        user = get_user_model().objects.create_user(
            username="alice", email="alice@example.com", display_name="Alice"
        )
        self.client.force_authenticate(user)
        response = self.client.get("/api/v1/me/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["email"], "alice@example.com")

    def test_anonymous_gets_error_shape(self):
        response = self.client.get("/api/v1/me/")
        self.assertEqual(response.json()["error"]["code"], "not_authenticated")
