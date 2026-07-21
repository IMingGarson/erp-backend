from rest_framework import status, viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from factory.models import User, UserProfile
from factory.permissions import IsEmployerOrReadOnly
from factory.serializers import (
    CustomTokenObtainPairSerializer,
    UserCreateSerializer,
    UserProfileSerializer,
    UserUpdateSerializer,
)


class LoginView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer


class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        return Response(
            {
                "id": user.id,
                "username": user.username,
                "department": user.profile.department
                if hasattr(user, "profile")
                else None,
                "is_active": user.is_active,
            }
        )


class LogoutView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        try:
            refresh_token = request.data.get("refresh")
            if not refresh_token:
                return Response(
                    {"error": "Refresh token is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            token = RefreshToken(refresh_token)
            token.blacklist()

            return Response(
                {"message": "登出成功"}, status=status.HTTP_205_RESET_CONTENT
            )
        except Exception:
            return Response(
                {"error": "Token 無效或已過期"}, status=status.HTTP_400_BAD_REQUEST
            )


class UserProfileViewSet(viewsets.ModelViewSet):
    queryset = (
        UserProfile.objects.filter(is_active=True)
        .select_related("user")
        .order_by("-id")
    )

    def get_permissions(self):
        return [IsAuthenticated(), IsEmployerOrReadOnly()]

    def get_serializer_class(self):
        if self.action == "create":
            return UserCreateSerializer
        elif self.action in ["update", "partial_update"]:
            return UserUpdateSerializer
        return UserProfileSerializer

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save()

        user = instance.user
        user.is_active = False
        user.save()


class AddMockUserView(APIView):
    def get_permissions(self):
        return [AllowAny()]

    def get(self, request):
        employer = User.objects.create_user(
            username="boss123",
            password="password123",
            first_name="余",
            last_name="老闆",
        )
        UserProfile.objects.create(user=employer, department="EMPLOYER")

        return Response(
            {"message": "老闆測試帳號 (boss123) 建立成功！"},
            status=status.HTTP_201_CREATED,
        )
