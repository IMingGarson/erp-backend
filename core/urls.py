from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from factory.auth.views import (
    AddMockUserView,
    CurrentUserView,
    LoginView,
    LogoutView,
    UserProfileViewSet,
)
from factory.mock import InitMockDataAPIView
from factory.views import (
    BatchInventoryViewSet,
    BOMViewSet,
    CustomerOrderViewSet,
    DeliveryNoteViewSet,
    MaterialRequirementPlanViewSet,
    MaterialViewSet,
    ProductionOrderViewSet,
    PurchaseRequisitionViewSet,
    VendorViewSet,
)

router = DefaultRouter(trailing_slash=False)
router.register(
    r"production_orders", ProductionOrderViewSet, basename="production-orders"
)
router.register(r"materials", MaterialViewSet, basename="material")
router.register(r"batches", BatchInventoryViewSet, basename="batch")
router.register(r"boms", BOMViewSet, basename="bom")
router.register(r"vendors", VendorViewSet, basename="vendor")
router.register(r"mrp", MaterialRequirementPlanViewSet, basename="mrp")
router.register(
    r"purchase_requisitions", PurchaseRequisitionViewSet, basename="purchase-requestion"
)
router.register(r"users", UserProfileViewSet, basename="users")
router.register(r"delivery_notes", DeliveryNoteViewSet, basename="delivery-notes")
router.register(r"customer_orders", CustomerOrderViewSet, basename="customer-orders")


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include(router.urls)),
    path("api/auth/login", LoginView.as_view(), name="login"),
    path("api/auth/refresh", TokenRefreshView.as_view(), name="refresh"),
    path("api/auth/logout", LogoutView.as_view(), name="logout"),
    path("api/auth/me", CurrentUserView.as_view(), name="me"),
]


dev_urlpatterns = [
    path(
        "api/add-employer-account",
        AddMockUserView.as_view(),
        name="add-employer-account",
    ),
    path("api/init-mock-data", InitMockDataAPIView.as_view(), name="import_sheets"),
]

if getattr(settings, "ENV", "dev") == "dev":
    urlpatterns += dev_urlpatterns
