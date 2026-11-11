from rest_framework.permissions import BasePermission, SAFE_METHODS

class IsOwnerOrReadOnly(BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        return obj.user == request.user


class IsUploaderOrReadOnly(BasePermission):
    """ Users can only edit/delete their own spot photos.
        Anyone can read them. """
    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        return obj.uploaded_by == request.user or request.user.is_staff


class IsSelfOrAdmin(BasePermission):
    """ Users can only edit/delete their own account.
        Admins can edit anyone. """
    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        return obj == request.user or request.user.is_staff