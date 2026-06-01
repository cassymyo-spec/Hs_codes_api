from dataclasses import asdict

from django.conf import settings
from django.contrib.postgres.search import TrigramSimilarity

from rest_framework import generics
from rest_framework.exceptions import ValidationError

from .models import HsCode

from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .permissions import IsAdminOrStaff
from .serializers import HsCodeUploadSerializer, HsCodeSerializer
from .services.file_upload_service import process_hs_code_csv


class HsCodeUploadView(APIView):
    parser_classes = [MultiPartParser]
    # permission_classes = [IsAdminOrStaff]

    def post(self, request):
        serializer = HsCodeUploadSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            result = process_hs_code_csv(
                uploaded_file=serializer.validated_data["file"]
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(asdict(result), status=status.HTTP_201_CREATED)


class HsCodeSearchView(generics.ListAPIView):
    serializer_class = HsCodeSerializer

    def get_queryset(self):
        q = self.request.query_params.get("q")

        if not q:
            raise ValidationError({"q": ["This query parameter is required."]})

        threshold = getattr(
            settings,
            "HS_CODE_SEARCH_THRESHOLD",
            0.1,
        )

        return (
            HsCode.objects.annotate(
                similarity=(
                    TrigramSimilarity("description", q) * 2
                    + TrigramSimilarity("hs_code", q)
                )
            )
            .filter(similarity__gte=threshold)
            .order_by("-similarity")
        )
