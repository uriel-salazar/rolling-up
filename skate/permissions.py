from rest_framework.permissions import BasePermission, SAFE_METHODS

SPECIAL_IMAGE_MANAGER_EMAIL = 'urieelsalazarr@gmail.com'


def is_special_image_manager(user):
    return bool(
        user
        and user.is_authenticated
        and user.email
        and user.email.strip().lower() == SPECIAL_IMAGE_MANAGER_EMAIL
    )


class IsOwnerOrReadOnly(BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        return obj.user == request.user


class IsOwnerOrReadOnlyOrSpotImageManager(BasePermission):
    """Owners can edit their spots; the maintainer can update the standard spot form on any spot."""

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True

        if obj.user == request.user or getattr(request.user, 'is_staff', False):
            return True

        if not is_special_image_manager(request.user):
            return False

        if request.method not in {'PATCH', 'PUT'}:
            return False

        data = request.data
        if not hasattr(data, 'keys'):
            return False

        allowed_fields = {
            'name_spot',
            'body',
            'category',
            'latitude',
            'longitude',
            'image_url',
        }
        changed_fields = set(data.keys())
        return bool(changed_fields) and changed_fields.issubset(allowed_fields)


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