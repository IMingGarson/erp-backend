from rest_framework import permissions


class IsEmployerOrReadOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True

        if not bool(request.user and request.user.is_authenticated):
            return False

        return bool(
            hasattr(request.user, "profile")
            and request.user.profile.department.upper() == "EMPLOYER"
        )


class IsAdminOrEmployerOrReadOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True

        return bool(
            request.user
            and request.user.is_authenticated
            and hasattr(request.user, "profile")
            and request.user.profile.department.upper() in ["ADMIN", "EMPLOYER"]
        )


class IsRDOrReadOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True

        return bool(
            request.user
            and request.user.is_authenticated
            and hasattr(request.user, "profile")
            and request.user.profile.department.upper() in ["RD"]
        )
