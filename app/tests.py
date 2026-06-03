import csv
import io

from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from app.models import HsCode, HsCodeFile, User
from app.services.file_upload_service import (
    UploadResult,
    _build_objects,
    _decode_file,
    _parse_csv,
    process_hs_code_csv,
)


def _make_csv_file(rows: list[dict], filename="hs_codes.csv") -> io.BytesIO:
    """Build an in-memory CSV file with the correct headers."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["HS CODE", "GOODS DESCRIPTION"])
    writer.writeheader()
    writer.writerows(rows)
    encoded = buf.getvalue().encode("utf-8")
    f = io.BytesIO(encoded)
    f.name = filename
    return f


def _make_uploaded_file(rows: list[dict]):
    """Return a Django-compatible InMemoryUploadedFile-like object."""
    from django.core.files.uploadedfile import InMemoryUploadedFile

    raw = _make_csv_file(rows)
    return InMemoryUploadedFile(
        file=raw,
        field_name="file",
        name="hs_codes.csv",
        content_type="text/csv",
        size=raw.getbuffer().nbytes,
        charset="utf-8",
    )


SAMPLE_ROWS = [
    {"HS CODE": "0101.21.00", "GOODS DESCRIPTION": "Live pure-bred breeding horses"},
    {"HS CODE": "0101.29.00", "GOODS DESCRIPTION": "Other live horses"},
    {
        "HS CODE": "0201.10.00",
        "GOODS DESCRIPTION": "Carcasses and half-carcasses of bovine",
    },
]


class DecodeFileTest(TestCase):
    def test_utf8_file_decoded(self):
        f = io.BytesIO(b"hello world")
        f.name = "test.csv"
        # Attach a read method compatible with _decode_file
        result = _decode_file(f)
        self.assertEqual(result, "hello world")

    def test_utf8_sig_bom_stripped(self):
        bom = b"\xef\xbb\xbfHS CODE,GOODS DESCRIPTION\n"
        f = io.BytesIO(bom)
        f.name = "bom.csv"
        result = _decode_file(f)
        self.assertFalse(result.startswith("\ufeff"))
        self.assertTrue(result.startswith("HS CODE"))

    def test_bad_encoding_raises_value_error(self):
        bad = io.BytesIO(b"\xff\xfe invalid latin sequence \x80\x81")
        bad.name = "bad.csv"
        with self.assertRaises(ValueError) as ctx:
            _decode_file(bad)
        self.assertIn("encoding", str(ctx.exception).lower())


class ParseCsvTest(TestCase):
    def _csv_text(self, rows, headers=None):
        headers = headers or ["HS CODE", "GOODS DESCRIPTION"]
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)
        return buf.getvalue()

    def test_valid_csv_returns_rows(self):
        text = self._csv_text(SAMPLE_ROWS)
        rows = _parse_csv(text)
        self.assertEqual(len(rows), 3)

    def test_missing_hs_code_column_raises(self):
        text = self._csv_text(
            [{"GOODS DESCRIPTION": "something"}],
            headers=["GOODS DESCRIPTION"],
        )
        with self.assertRaises(ValueError) as ctx:
            _parse_csv(text)
        self.assertIn("HS CODE", str(ctx.exception))

    def test_missing_description_column_raises(self):
        text = self._csv_text(
            [{"HS CODE": "0101.21.00"}],
            headers=["HS CODE"],
        )
        with self.assertRaises(ValueError):
            _parse_csv(text)

    def test_empty_csv_raises(self):
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=["HS CODE", "GOODS DESCRIPTION"])
        writer.writeheader()
        with self.assertRaises(ValueError) as ctx:
            _parse_csv(buf.getvalue())
        self.assertIn("no data", str(ctx.exception).lower())


class BuildObjectsTest(TestCase):
    def setUp(self):
        self.hs_file = HsCodeFile.objects.create(hs_code_file="hs_code/test.csv")

    def test_builds_correct_count(self):
        rows = [
            {"HS CODE": "0101.21.00", "GOODS DESCRIPTION": "Horses"},
            {"HS CODE": "0201.10.00", "GOODS DESCRIPTION": "Beef carcasses"},
        ]
        objects, skipped = _build_objects(rows, self.hs_file)
        self.assertEqual(len(objects), 2)
        self.assertEqual(skipped, 0)

    def test_skips_blank_hs_code(self):
        rows = [
            {"HS CODE": "", "GOODS DESCRIPTION": "Missing code"},
            {"HS CODE": "0101.21.00", "GOODS DESCRIPTION": "Horses"},
        ]
        objects, skipped = _build_objects(rows, self.hs_file)
        self.assertEqual(len(objects), 1)
        self.assertEqual(skipped, 1)

    def test_skips_blank_description(self):
        rows = [
            {"HS CODE": "0101.21.00", "GOODS DESCRIPTION": ""},
        ]
        objects, skipped = _build_objects(rows, self.hs_file)
        self.assertEqual(len(objects), 0)
        self.assertEqual(skipped, 1)

    def test_skips_whitespace_only_fields(self):
        rows = [
            {"HS CODE": "   ", "GOODS DESCRIPTION": "   "},
        ]
        objects, skipped = _build_objects(rows, self.hs_file)
        self.assertEqual(skipped, 1)

    def test_objects_have_correct_hs_code_file(self):
        rows = [{"HS CODE": "0101.21.00", "GOODS DESCRIPTION": "Horses"}]
        objects, _ = _build_objects(rows, self.hs_file)
        self.assertEqual(objects[0].hs_code_file, self.hs_file)


class ProcessHsCodeCsvTest(TestCase):
    def test_creates_records_and_returns_result(self):
        uploaded = _make_uploaded_file(SAMPLE_ROWS)
        result = process_hs_code_csv(uploaded_file=uploaded)

        self.assertIsInstance(result, UploadResult)
        self.assertEqual(result.created, 3)
        self.assertEqual(result.skipped_duplicates, 0)
        self.assertEqual(result.skipped_blank_rows, 0)
        self.assertEqual(result.total_rows, 3)
        self.assertEqual(HsCode.objects.count(), 3)

    def test_duplicate_codes_are_skipped(self):
        # First upload
        uploaded = _make_uploaded_file(SAMPLE_ROWS)
        process_hs_code_csv(uploaded_file=uploaded)

        # Second upload with same codes
        uploaded2 = _make_uploaded_file(SAMPLE_ROWS)
        result = process_hs_code_csv(uploaded_file=uploaded2)

        self.assertEqual(result.skipped_duplicates, 3)
        self.assertEqual(HsCode.objects.count(), 3)  # no new records

    def test_partial_duplicates_counted_correctly(self):
        uploaded = _make_uploaded_file(SAMPLE_ROWS[:2])
        process_hs_code_csv(uploaded_file=uploaded)

        # Upload all 3; 2 are duplicates
        uploaded2 = _make_uploaded_file(SAMPLE_ROWS)
        result = process_hs_code_csv(uploaded_file=uploaded2)

        self.assertEqual(result.created, 1)
        self.assertEqual(result.skipped_duplicates, 2)

    def test_creates_hs_code_file_record(self):
        uploaded = _make_uploaded_file(SAMPLE_ROWS)
        process_hs_code_csv(uploaded_file=uploaded)
        self.assertEqual(HsCodeFile.objects.count(), 1)

    def test_invalid_csv_raises_value_error(self):
        f = io.BytesIO(b"WRONG_COL,ANOTHER_COL\nfoo,bar")
        f.name = "bad.csv"
        from django.core.files.uploadedfile import InMemoryUploadedFile

        bad_file = InMemoryUploadedFile(f, "file", "bad.csv", "text/csv", 20, "utf-8")
        with self.assertRaises(ValueError):
            process_hs_code_csv(uploaded_file=bad_file)


class HsCodeUploadViewTest(APITestCase):
    url = "/api/v1/hs-codes/upload/"

    def _post_csv(self, rows):
        csv_file = _make_csv_file(rows)
        return self.client.post(
            self.url,
            {"file": csv_file},
            format="multipart",
        )

    def test_upload_valid_csv_returns_201(self):
        response = self._post_csv(SAMPLE_ROWS)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_upload_response_contains_expected_keys(self):
        response = self._post_csv(SAMPLE_ROWS)
        data = response.json()
        self.assertIn("created", data)
        self.assertIn("skipped_duplicates", data)
        self.assertIn("skipped_blank_rows", data)
        self.assertIn("total_rows", data)
        self.assertIn("hs_code_file_id", data)

    def test_upload_creates_correct_count(self):
        response = self._post_csv(SAMPLE_ROWS)
        self.assertEqual(response.json()["created"], 3)
        self.assertEqual(HsCode.objects.count(), 3)

    def test_upload_no_file_returns_400(self):
        response = self.client.post(self.url, {}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_upload_wrong_columns_returns_400(self):
        buf = io.BytesIO(b"WRONG,COLS\nfoo,bar")
        buf.name = "bad.csv"
        response = self.client.post(self.url, {"file": buf}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.json())

    def test_upload_empty_csv_body_returns_400(self):
        buf = io.BytesIO(b"HS CODE,GOODS DESCRIPTION\n")
        buf.name = "empty.csv"
        response = self.client.post(self.url, {"file": buf}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_duplicate_upload_returns_201_with_skipped(self):
        self._post_csv(SAMPLE_ROWS)
        response = self._post_csv(SAMPLE_ROWS)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.json()["skipped_duplicates"], 3)
        self.assertEqual(response.json()["created"], 0)


class HsCodeSearchViewTest(APITestCase):
    url = "/api/v1/hs-codes/"

    @classmethod
    def setUpTestData(cls):
        hs_file = HsCodeFile.objects.create(hs_code_file="hs_code/test.csv")
        HsCode.objects.bulk_create(
            [
                HsCode(
                    hs_code="0101.21.00",
                    description="Live pure-bred breeding horses",
                    hs_code_file=hs_file,
                ),
                HsCode(
                    hs_code="0101.29.00",
                    description="Other live horses",
                    hs_code_file=hs_file,
                ),
                HsCode(
                    hs_code="0201.10.00",
                    description="Carcasses and half-carcasses of bovine animals",
                    hs_code_file=hs_file,
                ),
                HsCode(
                    hs_code="8471.30.00",
                    description="Portable automatic data processing machines",
                    hs_code_file=hs_file,
                ),
            ]
        )

    def test_search_missing_q_returns_400(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_search_empty_q_returns_400(self):
        response = self.client.get(self.url, {"q": ""})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_search_returns_200(self):
        response = self.client.get(self.url, {"q": "horses"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_search_results_are_list(self):
        response = self.client.get(self.url, {"q": "horses"})
        self.assertIsInstance(response.json(), list)

    def test_search_hs_code_direct_match(self):
        response = self.client.get(self.url, {"q": "0101.21.00"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        codes = [r["hs_code"] for r in response.json()]
        self.assertIn("0101.21.00", codes)

    def test_search_no_results_returns_empty_list(self):
        response = self.client.get(self.url, {"q": "xyznonexistentterm12345"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json(), [])

    def test_search_result_has_expected_fields(self):
        response = self.client.get(self.url, {"q": "horses"})
        results = response.json()
        if results:
            self.assertIn("hs_code", results[0])
            self.assertIn("description", results[0])


class HealthCheckViewTest(APITestCase):
    url = "/api/v1/health/"

    def test_health_returns_200(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_health_returns_correct_body(self):
        response = self.client.get(self.url)
        self.assertEqual(response.json(), {"status": "healthy"})

    def test_health_requires_no_auth(self):
        # Even if session auth is default, health should be open
        self.client.logout()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class HsCodeModelTest(TestCase):
    def setUp(self):
        self.hs_file = HsCodeFile.objects.create(hs_code_file="hs_code/test.csv")

    def test_unique_constraint_on_hs_code(self):
        from django.db import IntegrityError

        HsCode.objects.create(
            hs_code="0101.21.00",
            description="Horses",
            hs_code_file=self.hs_file,
        )
        with self.assertRaises(IntegrityError):
            HsCode.objects.create(
                hs_code="0101.21.00",
                description="Different description",
                hs_code_file=self.hs_file,
            )

    def test_cascade_delete_removes_hs_codes(self):
        HsCode.objects.create(
            hs_code="0101.21.00",
            description="Horses",
            hs_code_file=self.hs_file,
        )
        self.assertEqual(HsCode.objects.count(), 1)
        self.hs_file.delete()
        self.assertEqual(HsCode.objects.count(), 0)


class IsAdminOrStaffPermissionTest(TestCase):
    def test_admin_role_allowed(self):
        from app.permissions import IsAdminOrStaff
        from unittest.mock import MagicMock

        perm = IsAdminOrStaff()
        request = MagicMock()
        request.user.is_authenticated = True
        request.user.role = "Admin"
        self.assertTrue(perm.has_permission(request, MagicMock()))

    def test_staff_role_allowed(self):
        from app.permissions import IsAdminOrStaff
        from unittest.mock import MagicMock

        perm = IsAdminOrStaff()
        request = MagicMock()
        request.user.is_authenticated = True
        request.user.role = "Staff"
        self.assertTrue(perm.has_permission(request, MagicMock()))

    def test_unknown_role_denied(self):
        from app.permissions import IsAdminOrStaff
        from unittest.mock import MagicMock

        perm = IsAdminOrStaff()
        request = MagicMock()
        request.user.is_authenticated = True
        request.user.role = "Guest"
        self.assertFalse(perm.has_permission(request, MagicMock()))

    def test_unauthenticated_denied(self):
        from app.permissions import IsAdminOrStaff
        from unittest.mock import MagicMock

        perm = IsAdminOrStaff()
        request = MagicMock()
        request.user.is_authenticated = False
        self.assertFalse(perm.has_permission(request, MagicMock()))
