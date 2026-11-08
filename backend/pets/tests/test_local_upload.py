"""The full upload flow against the real local storage backend in a temp folder.

No storage patching: the API issues local signed URLs, `api.local_files.serve`
plays the browser's PUT and GET, and `complete` reads the stored sidecar.
"""

import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.signals import request_finished
from django.db import close_old_connections
from django.test import RequestFactory, override_settings
from rest_framework.test import APITestCase

from api.local_files import serve
from pets.models import Pet, PetDocument

from .base import API

LOCAL_URL = "http://testserver/api/v1/local-files/"
PDF_BYTES = b"%PDF-1.4\n" + bytes(range(256)) * 300 + b"\n%%EOF\n"
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 2048


class LocalUploadFlowTests(APITestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.enterContext(
            override_settings(
                PET_FILES_BACKEND="local",
                PET_FILES_LOCAL_DIR=str(self.root),
                PET_FILES_LOCAL_URL=LOCAL_URL,
            )
        )
        self.factory = RequestFactory()
        self.user = get_user_model().objects.create_user(username="carol")
        self.client.force_authenticate(self.user)
        self.pet = Pet.objects.create(owner=self.user, name="Biscuit", species=Pet.DOG)

    @staticmethod
    def token_of(url):
        assert url.startswith(LOCAL_URL) and url.endswith("/"), url
        return url.removeprefix(LOCAL_URL).removesuffix("/")

    def put(self, url, body, content_type):
        token = self.token_of(url)
        request = self.factory.put(
            f"/api/v1/local-files/{token}/", data=body, content_type=content_type
        )
        return serve(request, token)

    def get(self, url):
        token = self.token_of(url)
        response = serve(self.factory.get(f"/api/v1/local-files/{token}/"), token)
        try:
            body = b"".join(response.streaming_content) if response.streaming else b""
        finally:
            # An open handle would break temp-dir cleanup on Windows. close()
            # fires request_finished, whose close_old_connections would drop the
            # test transaction's connection; Django's test client disconnects it
            # around close() in the same way.
            request_finished.disconnect(close_old_connections)
            try:
                response.close()
            finally:
                request_finished.connect(close_old_connections)
        return response, body

    def test_document_round_trip(self):
        documents = f"{API}pets/{self.pet.pk}/documents/"
        response = self.client.post(
            documents,
            {
                "title": "Rabies certificate",
                "filename": "certificate.pdf",
                "content_type": "application/pdf",
                "size_bytes": len(PDF_BYTES),
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        ticket = response.json()
        doc_id = ticket["document"]["id"]
        self.assertEqual(ticket["upload_headers"], {"Content-Type": "application/pdf"})

        # Completing before the PUT is a 409; the row stays pending
        response = self.client.post(f"{documents}{doc_id}/complete/")
        self.assertEqual(response.status_code, 409, response.content)

        upload = self.put(ticket["upload_url"], PDF_BYTES, "application/pdf")
        self.assertEqual(upload.status_code, 200, upload.content)

        response = self.client.post(f"{documents}{doc_id}/complete/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["status"], "ready")

        response = self.client.get(documents)
        self.assertEqual(response.status_code, 200)
        [row] = response.json()["results"]
        self.assertEqual(row["id"], doc_id)

        download, body = self.get(row["download_url"])
        self.assertEqual(download.status_code, 200)
        self.assertEqual(body, PDF_BYTES)
        self.assertEqual(download["Content-Type"], "application/pdf")
        self.assertEqual(
            download["Content-Disposition"], 'attachment; filename="pet-document.pdf"'
        )
        self.assertEqual(download["Cache-Control"], "no-store")

        # Deleting the document removes the stored file after commit
        key = PetDocument.objects.get(pk=doc_id).file_key
        self.assertTrue((self.root / key).is_file())
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.delete(f"{documents}{doc_id}/")
        self.assertEqual(response.status_code, 204)
        self.assertFalse((self.root / key).exists())
        missing, _ = self.get(row["download_url"])
        self.assertEqual(missing.status_code, 404)

    def test_wrong_content_type_put_is_rejected_and_complete_waits(self):
        documents = f"{API}pets/{self.pet.pk}/documents/"
        response = self.client.post(
            documents,
            {"title": "Scan", "content_type": "application/pdf", "size_bytes": 3},
            format="json",
        )
        ticket = response.json()
        upload = self.put(ticket["upload_url"], b"abc", "image/png")
        self.assertEqual(upload.status_code, 403)
        response = self.client.post(f"{documents}{ticket['document']['id']}/complete/")
        self.assertEqual(response.status_code, 409, response.content)

    def test_photo_round_trip(self):
        pet_url = f"{API}pets/{self.pet.pk}/"
        response = self.client.post(
            f"{pet_url}photo-upload/",
            {"content_type": "image/png", "size_bytes": len(PNG_BYTES)},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        upload = self.put(response.json()["upload_url"], PNG_BYTES, "image/png")
        self.assertEqual(upload.status_code, 200, upload.content)

        response = self.client.post(f"{pet_url}photo-upload/complete/")
        self.assertEqual(response.status_code, 200, response.content)
        photo_url = response.json()["photo_url"]
        self.assertIsNotNone(response.json()["photo_version"])

        download, body = self.get(photo_url)
        self.assertEqual(download.status_code, 200)
        self.assertEqual(body, PNG_BYTES)
        self.assertEqual(download["Content-Type"], "image/png")
        self.assertEqual(download["Content-Disposition"], "inline")
