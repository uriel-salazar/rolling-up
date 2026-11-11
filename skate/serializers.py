from rest_framework import serializers
from .models import User,Spots,Rating
from decimal import Decimal
from django.contrib.auth.password_validation import validate_password
from skate.media_api.images_skateparks import image_logic
from django.core.files.base import ContentFile


class CoordinateField(serializers.DecimalField):
    """A decimal coordinate that tolerates an empty value.

    HTML forms submit an empty string when the user clears a field, so
    an empty value is treated the same way as ``NULL`` instead of
    raising a "a valid number is required" error. This is what lets a
    user remove the location of a spot.
    """

    def __init__(self, **kwargs):
        kwargs.setdefault('max_digits', 10)
        kwargs.setdefault('decimal_places', 6)
        kwargs.setdefault('required', False)
        kwargs.setdefault('allow_null', True)
        super().__init__(**kwargs)

    def run_validation(self, data=serializers.empty):
        """Return ``None`` for an empty value instead of failing."""
        if isinstance(data, str) and not data.strip():
            return None
        return super().run_validation(data)


class UserSerializer(serializers.ModelSerializer):
    """ User serializer with validation of password, hashing of password,
        and validation of username. 
    
    """
    
    password = serializers.CharField(write_only=True)
    email = serializers.EmailField(write_only=True)
    # email and password are never exposed in responses
    class Meta:
        model = User
        fields = ['id','username','email','password','created_at']

    def validate_password(self, value):
        """
        Add password validation from settings.py
        Password requirements : 
        It must have at least 8 words length 
        - It doens't have to be too common 
        """
        validate_password(value) 
        return value
    
    def create(self, validated_data):
        """ Create user and save their password
        """
        user = User(
            username=validated_data['username'],
            email=validated_data['email'],
        )
        user.set_password(validated_data['password'])
        user.save()
        return user

    def update(self, instance, validated_data):
        """ Hash the password before updating the user
        """
        password = validated_data.pop('password', None)
        user = super().update(instance, validated_data)
        if password:
            user.set_password(password)
            user.save()
        return user
    
    def validate_username(self, username):
        """ 
        Username must have at least 5 words. 

        Raises:
            serializers.ValidationError: validation if the username is less 
            than 5 words 

        Returns:
            username
        """
        if len(username) < 5:
            raise serializers.ValidationError(f"'{username}' must have at least 5 characters.")
        return username
class SpotSerializer(serializers.ModelSerializer):
    """ Serializer for spots.
        Includes function that turns images to a certain quality (85)
        and resize them. 
        Deletes original image file. 

    Args:
        serializers (_type_): _description_

    Returns:
        _type_: _description_
    """
    class Meta:
        model=Spots
        fields = [
            'id', 'name_spot', 'image_url', 'body', 'created_at',
            'latitude', 'longitude', 'source', 'osm_id', 'osm_type',
            'osm_metadata', 'user', 'category', 'rating', 'rating_count',
        ]
        # The provenance fields are managed by the importer, a user may
        # not set them through the API.
        read_only_fields = [
            'id', 'created_at', 'user', 'source',
            'osm_id', 'osm_type', 'osm_metadata', 'rating', 'rating_count',
        ]

    # The average of the ratings of the spot and how many there are.
    # They come from the annotations of the queryset, so they are only
    # there when the spots are read through the viewset.
    rating = serializers.SerializerMethodField()
    rating_count = serializers.SerializerMethodField()

    def get_rating(self, obj):
        """Return the average score of the spot, or None."""
        value = getattr(obj, 'average_rating', None)
        return float(value) if value is not None else None

    def get_rating_count(self, obj):
        """Return how many ratings the spot has."""
        return getattr(obj, 'rating_count', 0) or 0

    latitude = CoordinateField(
        min_value=Decimal('-90'), max_value=Decimal('90'),
        help_text='Latitude of the spot, between -90 and 90. Optional.',
    )
    longitude = CoordinateField(
        min_value=Decimal('-180'), max_value=Decimal('180'),
        help_text='Longitude of the spot, between -180 and 180. Optional.',
    )

    def validate(self, attrs):
        """Check that the two coordinates are either both set or both empty.

        The effective values are used, so a partial update that only
        sends one of the two is compared against the value that is
        already stored on the instance.
        """
        instance = self.instance

        latitude = attrs.get('latitude', getattr(instance, 'latitude', None))
        longitude = attrs.get('longitude', getattr(instance, 'longitude', None))

        if (latitude is None) != (longitude is None):
            raise serializers.ValidationError({
                'latitude': (
                    'Latitude and longitude must be sent together. '
                    'Send both of them to set a location, or neither of '
                    'them to leave the spot without one.'
                )
            })

        return attrs

    def validate_image_url(self, value):
        if value is None:
            return value

        max_size = 5 * 1024 * 1024
        if value.size > max_size:
            raise serializers.ValidationError("Image must be 5 MB or smaller.")

        allowed_types = {"image/jpeg", "image/png", "image/webp"}
        content_type = getattr(value, "content_type", None)
        if content_type not in allowed_types:
            raise serializers.ValidationError(
                "Unsupported image format. Use JPEG, PNG or WebP."
            )
        return value

    def _process_image(self, image):
        """ 
        Resize the uploaded image to 800x800 with quality 85 before it is
        stored, keeping the original file name.
        """
        try:
            image.seek(0)
            resized_image = image_logic.image_resize_800(image)
        except Exception:
            raise serializers.ValidationError(
                {"image_url": "Could not process the uploaded image."}
            )
        return ContentFile(resized_image.getvalue(), name=image.name)

    def create(self,validated_data):
        if validated_data.get('image_url'):
            validated_data['image_url'] = self._process_image(validated_data['image_url'])
        return super().create(validated_data)

    def update(self, instance, validated_data):
        old_image_name = instance.image_url.name if instance.image_url else None
        new_image = validated_data.get('image_url')

        if new_image:
            validated_data['image_url'] = self._process_image(new_image)

        instance = super().update(instance, validated_data)

        if new_image and old_image_name and old_image_name != instance.image_url.name:
            instance.image_url.storage.delete(old_image_name)

        return instance


class RatingSerializer(serializers.ModelSerializer):
    score = serializers.DecimalField(
        max_digits=4,
        decimal_places=2,
        # rating consists of 1 to 5 score
        min_value=Decimal('1'),
        max_value=Decimal('5'),
        coerce_to_string=False,
    )
    spot = serializers.PrimaryKeyRelatedField(queryset=Spots.objects.all())

    class Meta:
        model = Rating
        fields = "__all__"
        read_only_fields = ['id','created_at','user']
    
        
        
            
