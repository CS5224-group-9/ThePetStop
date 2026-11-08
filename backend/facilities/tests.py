import json
import time
from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from .models import Facility, FacilitySyncRun
from .onemap import (
    OneMapClient,
    SearchFailed,
    SearchTimeout,
    SearchUnavailable,
    _request_json,
    _TokenRejected,
)

ROW = {
    "ADDRESS": "640 ROWELL ROAD SINGAPORE 200640",
    "POSTAL": "200640",
    "LATITUDE": "1.30743547948389",
    "LONGITUDE": "103.854713903431",
}


def token():
    return {"access_token": "test-token", "expiry_timestamp": str(time.time() + 3600)}


@override_settings(
    ONEMAP_EMAIL="test@example.test",
    ONEMAP_PASSWORD="test-password",
    ONEMAP_ACCESS_TOKEN="",
)
class OneMapTests(SimpleTestCase):
    def setUp(self):
        self.client = OneMapClient()

    @patch("facilities.onemap._request_json")
    def test_normalizes_deduplicates_and_reuses_token(self, request):
        request.side_effect = [token(), {"results": [ROW, ROW]}, {"results": []}]
        results = self.client.search("Rowell Road")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["postal_code"], "200640")
        self.assertAlmostEqual(results[0]["latitude"], 1.30743547948389)
        self.assertNotIn("access_token", results[0])
        self.assertEqual(self.client.search("nothing"), [])
        self.assertEqual(request.call_count, 3)
        self.assertIn("searchVal=Rowell+Road", request.call_args_list[1].args[0])
        self.assertEqual(request.call_args_list[1].kwargs["token"], "test-token")

    @patch("facilities.onemap._request_json")
    def test_refreshes_token_for_http_and_json_auth_errors(self, request):
        for rejection in [_TokenRejected(), {"error": "expired", "results": []}]:
            with self.subTest(rejection=type(rejection)):
                client = OneMapClient()
                request.side_effect = [token(), rejection, token(), {"results": [ROW]}]
                self.assertEqual(len(client.search("Rowell")), 1)
        request.side_effect = [
            token(),
            {"error": "invalid"},
            token(),
            {"error": "invalid"},
        ]
        with self.assertRaises(SearchUnavailable):
            OneMapClient().search("Rowell")

    @patch("facilities.onemap._request_json")
    def test_renews_expired_token(self, request):
        request.side_effect = [token(), {"results": []}, token(), {"results": []}]
        self.client.search("Rowell")
        self.client._expires = time.time() - 1
        self.client.search("Rowell")
        self.assertEqual(request.call_count, 4)

    @override_settings(ONEMAP_ACCESS_TOKEN="existing-token")
    @patch("facilities.onemap._request_json")
    def test_supplied_token_is_used_until_rejected_then_replacement_is_reused(
        self, request
    ):
        request.side_effect = [
            {"results": []},
            {"error": "expired"},
            token(),
            {"results": [ROW]},
            {"results": []},
        ]
        self.client.search("Bishan")
        self.assertEqual(request.call_count, 1)
        self.assertEqual(request.call_args.kwargs["token"], "existing-token")
        self.assertEqual(len(self.client.search("Rowell")), 1)
        self.client.search("Bishan")
        self.assertEqual(request.call_count, 5)
        self.assertEqual(request.call_args.kwargs["token"], "test-token")

    @override_settings(
        ONEMAP_ACCESS_TOKEN="existing-token", ONEMAP_EMAIL="", ONEMAP_PASSWORD=""
    )
    @patch("facilities.onemap._request_json")
    def test_token_only_setup_works_but_requires_credentials_after_expiry(
        self, request
    ):
        request.side_effect = [{"results": []}, _TokenRejected()]
        self.client.search("Bishan")
        with self.assertRaises(SearchUnavailable):
            self.client.search("Bishan")
        with self.assertRaises(SearchUnavailable):
            self.client.search("Bishan")
        self.assertEqual(request.call_count, 2)
        with self.settings(ONEMAP_ACCESS_TOKEN="manually-replaced-token"):
            request.side_effect = [{"results": []}]
            self.client.search("Bishan")
            self.assertEqual(
                request.call_args.kwargs["token"], "manually-replaced-token"
            )

    @patch("facilities.onemap._request_json")
    def test_unexpired_generated_token_is_not_refreshed_early(self, request):
        request.side_effect = [token(), {"results": []}, {"results": []}]
        self.client.search("Bishan")
        self.client._expires = time.time() + 30
        self.client.search("Bishan")
        self.assertEqual(request.call_count, 3)

    @override_settings(ONEMAP_EMAIL="", ONEMAP_PASSWORD="")
    @patch("facilities.onemap._request_json")
    def test_missing_configuration_never_calls_onemap(self, request):
        with self.assertRaises(SearchUnavailable):
            self.client.search("Bishan")
        request.assert_not_called()

    @patch("facilities.onemap._request_json")
    def test_validates_payload_and_bounds_results(self, request):
        request.side_effect = [
            token(),
            {"results": [dict(ROW, ADDRESS=str(n)) for n in range(30)]},
        ]
        self.assertEqual(len(self.client.search("Rowell")), 10)
        for payload in [
            {},
            {"results": "bad"},
            {"results": [dict(ROW, LATITUDE="NaN")]},
            {"results": [dict(ROW, LONGITUDE="0")]},
        ]:
            request.side_effect = [token(), payload]
            with self.assertRaises(SearchFailed):
                OneMapClient().search("Rowell")

    @patch("facilities.onemap.HTTPSConnection")
    def test_transport_is_bounded_and_closes_connections(self, connection):
        conn = connection.return_value
        response = conn.getresponse.return_value
        response.status = 200
        response.read.return_value = json.dumps({"results": []}).encode()
        self.assertEqual(_request_json("/test", token="secret"), {"results": []})
        connection.assert_called_with("www.onemap.gov.sg", timeout=4)
        response.read.assert_called_with(1_000_001)
        conn.close.assert_called()
        conn.request.side_effect = TimeoutError()
        with self.assertRaises(SearchTimeout):
            _request_json("/test")
        conn.request.side_effect = OSError("private network details")
        with self.assertRaises(SearchUnavailable):
            _request_json("/test")

    @patch("facilities.onemap.HTTPSConnection")
    def test_transport_rejects_redirects_malformed_json_and_oversized_responses(
        self, connection
    ):
        response = connection.return_value.getresponse.return_value
        for status, payload, exception in [
            (302, b"", SearchUnavailable),
            (401, b"", _TokenRejected),
            (200, b"oops", SearchFailed),
            (200, b"x" * 1_000_001, SearchFailed),
            (200, b"[]", SearchFailed),
        ]:
            response.status, response.read.return_value = status, payload
            with self.assertRaises(exception):
                _request_json("/test")


class FacilityListViewTests(TestCase):
    def setUp(self):
        run = FacilitySyncRun.objects.create(source="vet")
        self.facility = Facility.objects.create(
            source_id="vet",
            source_key="test-vet",
            facility_type="vet",
            name="Bishan Veterinary Centre",
            address="1 Bishan Street",
            postal_code="570001",
            latitude="1.350000",
            longitude="103.840000",
            source="AVS",
            source_url="https://example.test/registry",
            source_document_url="https://example.test/registry.pdf",
            last_checked_at=timezone.now(),
            active=True,
            last_seen_run=run,
        )
        Facility.objects.create(
            source_id="pet_shop",
            source_key="inactive-shop",
            facility_type="pet_shop",
            name="Inactive Shop",
            address="2 Bishan Street",
            postal_code="570002",
            source="AVS",
            source_url="https://example.test/registry",
            source_document_url="https://example.test/registry.pdf",
            last_checked_at=timezone.now(),
            active=False,
            last_seen_run=run,
        )

    def test_public_list_returns_active_registry_rows_and_no_store(self):
        response = APIClient().get(
            "/api/v1/facilities/", HTTP_AUTHORIZATION="Bearer invalid"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertEqual(response.json()["count"], 1)
        row = response.json()["results"][0]
        self.assertEqual(row["id"], str(self.facility.id))
        self.assertEqual(row["facility_type"], "vet")
        self.assertEqual(row["latitude"], "1.350000")
        self.assertEqual(row["verification_status"], "verified")
        self.assertIsNone(row["approved_animals"])
        self.assertNotIn("email", row)

    def test_filters_before_pagination_and_orders_by_distance(self):
        for index in range(25):
            Facility.objects.create(
                source_id="pet_shop",
                source_key=f"shop-{index}",
                facility_type="pet_shop",
                name=f"Shop {index:02}",
                address="Bishan",
                postal_code="570001",
                latitude=1.35 + index * 0.001,
                longitude=103.84,
                approved_animals=["cat"],
                source="AVS",
                source_url="https://example.test/registry",
                source_document_url="https://example.test/registry.pdf",
                last_checked_at=timezone.now(),
                last_seen_run=self.facility.last_seen_run,
            )
        response = APIClient().get(
            "/api/v1/facilities/",
            {
                "type": "pet_shop",
                "animal": "cat",
                "lat": 1.35,
                "lng": 103.84,
                "radius_km": 1,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 9)
        self.assertEqual(
            [row["name"] for row in response.json()["results"]],
            [f"Shop {index:02}" for index in range(9)],
        )

        page = (
            APIClient()
            .get(
                "/api/v1/facilities/",
                {
                    "type": "pet_shop",
                    "animal": "cat",
                    "lat": 1.35,
                    "lng": 103.84,
                    "radius_km": 5,
                },
            )
            .json()
        )
        self.assertEqual(page["count"], 25)
        self.assertIsNotNone(page["next"])
        self.assertEqual(
            [row["name"] for row in page["results"]],
            [f"Shop {index:02}" for index in range(20)],
        )

    def test_invalid_filter_parameters(self):
        for params in (
            {"lat": 1},
            {"radius_km": 5},
            {"lat": "nan", "lng": 2},
            {"type": "other"},
            {"animal": "horse"},
            {"lat": 1, "lng": 2, "radius_km": 0},
        ):
            self.assertEqual(
                APIClient().get("/api/v1/facilities/", params).status_code, 400
            )

    def test_list_is_read_only(self):
        self.assertEqual(APIClient().post("/api/v1/facilities/").status_code, 405)

    def test_pet_shop_approvals_are_public_and_vets_remain_unknown(self):
        self.facility.facility_type = "pet_shop"
        self.facility.approved_animals = ["dog", "cat"]
        self.facility.save()
        row = APIClient().get("/api/v1/facilities/").json()["results"][0]
        self.assertEqual(row["approved_animals"], ["dog", "cat"])


class LocationSearchViewTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

    @patch("facilities.views.client.search", return_value=[])
    def test_public_endpoint_and_no_store(self, search):
        response = self.client.get(
            "/api/v1/locations/search/",
            {"q": "  Bishan  "},
            HTTP_AUTHORIZATION="Bearer invalid",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"results": []})
        self.assertEqual(response["Cache-Control"], "no-store")
        search.assert_called_once_with("Bishan")

    @patch("facilities.views.client.search")
    def test_invalid_queries_do_not_call_upstream(self, search):
        for query in [{}, {"q": " "}, {"q": "a"}, {"q": "a" * 121}, {"q": "ab\x00c"}]:
            response = self.client.get("/api/v1/locations/search/", query)
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json()["error"]["code"], "invalid")
        search.assert_not_called()

    @patch("facilities.views.client.search", side_effect=SearchUnavailable())
    def test_upstream_failure_uses_shared_error_contract(self, search):
        response = self.client.get("/api/v1/locations/search/", {"q": "Bishan"})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json()["error"]["code"], "location_search_unavailable"
        )

    @patch("facilities.views.client.search", return_value=[])
    def test_throttles_and_rejects_writes(self, search):
        for _ in range(30):
            self.assertEqual(
                self.client.get(
                    "/api/v1/locations/search/", {"q": "Bishan"}
                ).status_code,
                200,
            )
        self.assertEqual(
            self.client.get("/api/v1/locations/search/", {"q": "Bishan"}).status_code,
            429,
        )
        self.assertEqual(search.call_count, 30)
        cache.clear()
        self.assertEqual(
            self.client.post("/api/v1/locations/search/", {"q": "Bishan"}).status_code,
            405,
        )
