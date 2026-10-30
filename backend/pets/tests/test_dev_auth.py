"""Cross-app smoke test: local dev sign-in still goes through pet ownership."""

from unittest import mock

from django.test import override_settings
from rest_framework.authentication import SessionAuthentication
from rest_framework.test import APITestCase
from rest_framework.views import APIView

from api.authentication import (
    CognitoAuthentication,
    DevAuthentication,
    get_dev_user,
)
from pets.models import Pet

from .base import API


@override_settings(ALLOWED_HOSTS=["localhost", "testserver"], DEV_AUTH_ENABLED=True)
class DevAuthPetOwnershipTests(APITestCase):
    def setUp(self):
        # override_settings(REST_FRAMEWORK=...) cannot work: DRF binds
        # APIView.authentication_classes at import, so patch the attribute the
        # pets generic views inherit.
        patcher = mock.patch.object(
            APIView,
            "authentication_classes",
            [CognitoAuthentication, DevAuthentication, SessionAuthentication],
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client.defaults["HTTP_HOST"] = "localhost:8000"
        self.pet = Pet.objects.create(
            owner=get_dev_user("alice"), name="Kopi", species=Pet.DOG
        )
        self.url = f"{API}pets/{self.pet.pk}/"

    def test_dev_bob_cannot_read_alices_pet(self):
        response = self.client.get(self.url, HTTP_AUTHORIZATION="Dev bob")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "not_found")
        response = self.client.get(f"{API}pets/", HTTP_AUTHORIZATION="Dev bob")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 0)

    def test_dev_alice_reads_her_pet(self):
        response = self.client.get(self.url, HTTP_AUTHORIZATION="Dev alice")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["name"], "Kopi")
