from django.urls import path
from .views import HsCodeUploadView, HsCodeSearchView

urlpatterns = [
    path(
        "hs-codes/",
        HsCodeSearchView.as_view(),
        name="hs-code-search",
    ),
    path("hs-codes/upload/", HsCodeUploadView.as_view(), name="hscode-upload"),
]
