from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.validators import UniqueValidator
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .models import User,Spots,Rating,SpotPhoto
from decimal import Decimal
from django.contrib.auth.password_validation import validate_password
from skate.media_api.images_skateparks import image_logic
from skate.media_api.images_skateparks.resolver import (
    google_data_is_fresh,
    resolve_spot_address,
    resolve_spot_image,
)
from django.core.files.base import ContentFile


class EmailOrUsernameTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Sign in with the username or with the email address.

        The login form asks for "usuario o correo", so the two are
        accepted. When the text is an email address it is translated
        into the username of the account before the credentials are
        checked.
    """

    def validate(self, attrs):
        identifier = attrs.get(self.username_field, '') or ''
        identifier = identifier.strip()

        if '@' in identifier:
            user = User.objects.filter(email__iexact=identifier).first()
            if user is None:
                raise AuthenticationFailed(
                    self.error_messages['no_active_account'],
                    'no_active_account',
                )
            attrs[self.username_field] = user.username

        return super().validate(attrs)


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
    # The email is unique in the database. Declaring the field by hand
    # drops the validator that the model serializer builds, so it is
    # added here: a duplicate address is answered with a 400 and not
    # with an IntegrityError of the database.
    email = serializers.EmailField(
        write_only=True,
        validators=[UniqueValidator(queryset=User.objects.all())],
    )
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
            'osm_metadata', 'google_place_id', 'google_metadata',
            'user', 'category', 'rating', 'rating_count',
            'image_attribution', 'image_license', 'image_license_url',
            'image_source', 'address',
        ]
        # The provenance fields are managed by the importer, a user may
        # not set them through the API.
        read_only_fields = [
            'id', 'created_at', 'user', 'source',
            'osm_id', 'osm_type', 'osm_metadata',
            'google_place_id', 'google_metadata', 'rating', 'rating_count',
        ]

    # The average of the ratings of the spot and how many there are.
    # They come from the annotations of the queryset, so they are only
    # there when the spots are read through the viewset.
    rating = serializers.SerializerMethodField()
    rating_count = serializers.SerializerMethodField()

    # The photograph is resolved from the uploaded file, Google Places
    # or the OpenStreetMap tags, without changing the ``image_url``
    # field the existing clients already read.
    image_attribution = serializers.SerializerMethodField()
    image_license = serializers.SerializerMethodField()
    image_license_url = serializers.SerializerMethodField()
    image_source = serializers.SerializerMethodField()
    address = serializers.SerializerMethodField()
    google_metadata = serializers.SerializerMethodField()

    def _resolved_image(self, obj):
        cache = getattr(self, '_image_cache', None)
        if cache is None:
            cache = {}
            self._image_cache = cache

        key = getattr(obj, 'pk', id(obj))
        if key not in cache:
            cache[key] = resolve_spot_image(obj, self.context.get('request'))
        return cache[key]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        image = self._resolved_image(instance)
        if image is None:
            data['image_url'] = None
        else:
            data['image_url'] = image.get('url')
        return data

    def get_image_attribution(self, obj):
        image = self._resolved_image(obj)
        return image.get('attribution') if image else None

    def get_image_license(self, obj):
        image = self._resolved_image(obj)
        return image.get('license') if image else None

    def get_image_license_url(self, obj):
        image = self._resolved_image(obj)
        return image.get('license_url') if image else None

    def get_image_source(self, obj):
        image = self._resolved_image(obj)
        return image.get('source') if image else None

    def get_address(self, obj):
        return resolve_spot_address(obj)

    def get_google_metadata(self, obj):
        """Do not expose provider content beyond its 30-day cache limit."""
        metadata = obj.google_metadata
        if not isinstance(metadata, dict):
            return None
        return metadata if google_data_is_fresh(metadata) else None

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
        """Keep the visual quality of uploaded photos without huge files."""
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


class SpotPhotoSerializer(serializers.ModelSerializer):
    """ Serializer for additional spot photographs.
        The uploader is read-only and is filled from the request user.
    """
    uploaded_by = serializers.PrimaryKeyRelatedField(read_only=True)
    # The spot of the photograph comes from the url of the endpoint,
    # so the client does not send it and can not put a photograph in
    # a spot it did not ask for.
    spot = serializers.PrimaryKeyRelatedField(read_only=True)
    # A photograph without a file is not a photograph.
    image = serializers.ImageField(required=True)

    class Meta:
        model = SpotPhoto
        fields = ['id', 'spot', 'image', 'caption', 'uploaded_by', 'created_at']
        read_only_fields = ['id', 'uploaded_by', 'created_at']

    def validate_image(self, value):
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

    def create(self, validated_data):
        validated_data['image'] = self._process_image(validated_data['image'])
        return super().create(validated_data)

    def _process_image(self, image):
        try:
            image.seek(0)
            resized_image = image_logic.image_resize_800(image)
        except Exception:
            raise serializers.ValidationError(
                {"image": "Could not process the uploaded image."}
            )
        return ContentFile(resized_image.getvalue(), name=image.name)


class RatingSerializer(serializers.ModelSerializer):
    score = serializers.DecimalField(
        max_digits=4,
        decimal_places=2,
        # rating consists of 1 to 5 score
        min_value=Decimal('1'),
        max_value=Decimal('5'),
        coerce_to_string=False,
    )
    comment = serializers.CharField(
        max_length=500,
        required=False,
        allow_blank=True,
        default='',
    )
    # The spot of a rating is fixed: a rating belongs to the spot it
    # was written for and it can not be moved to another one. The
    # endpoint of the spot fills the field.
    spot = serializers.PrimaryKeyRelatedField(read_only=True)
    user_username = serializers.SerializerMethodField()

    class Meta:
        model = Rating
        fields = "__all__"
        read_only_fields = ['id','created_at','user']

    def get_user_username(self, obj):
        """The name of the rider, so the list can be drawn without
        asking for the accounts one by one."""
        return obj.user.username if obj.user_id else ''

    def validate_score(self, value):
        """The stars are whole numbers, from one to five."""
        if value != value.to_integral_value():
            raise serializers.ValidationError(
                'The score has to be a whole number, from 1 to 5.'
            )
        return value
    
        
        
            
