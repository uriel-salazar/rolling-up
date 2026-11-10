from rest_framework import serializers
from .models import User,Spots,Rating
from decimal import Decimal
from django.contrib.auth.password_validation import validate_password
from skate.media_api.images_skateparks import image_logic
from django.core.files.base import ContentFile

class UserSerializer(serializers.ModelSerializer):
    """ User serializer with validation of password, hashing of password,
        and validation of username. 
    
    """
    
<<<<<<< HEAD
    password = serializers.CharField(write_only=True) 
<<<<<<< HEAD
=======
    email = serializers.CharField(write_only=True)
>>>>>>> develope
    #only user can see their password.
    class Meta:
        model = User
        fields = ['id','username','email','password','created_at']
    
    
    def validate_password(self, value):
=======
    password = serializers.CharField(write_only=True)
    email = serializers.EmailField(write_only=True)
    # email and password are never exposed in responses
    class Meta:
        model = User
        fields = ['id','username','email','password','created_at']

    def validate_password(self, value):
>>>>>>> develope
        """
        Add password validation from settings.py
        Password requirements : 
        It must have at least 8 words length 
        - It doens't have to be too common 
        """
        validate_password(value) 
        return value
    
    def create(self, validated_data):
<<<<<<< HEAD
<<<<<<< HEAD
=======
        """ Create user and save their password
        """
>>>>>>> develope
=======
        """ Create user and save their password
        """
>>>>>>> develope
        user = User(
            username=validated_data['username'],
            email=validated_data['email'],
        )
        user.set_password(validated_data['password'])  
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
<<<<<<< HEAD
        if len(username.split()) < 5:
            raise serializers.ValidationError(f"'{username}' must have at least 5 words.")
=======
        if len(username) < 5:
            raise serializers.ValidationError(f"'{username}' must have at least 5 characters.")
>>>>>>> develope
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
        fields = ['id', 'name_spot','image_url','body', 'created_at']
        read_only_fields = ['id','created_at','user']

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

<<<<<<< HEAD
<<<<<<< HEAD
    def _resize_image(self, instance):
        if not instance.image_url:
            return

        original_name = instance.image_url.name
        #function that resizes image 
        resized_image = image_logic.image_resize_800(instance.image_url)

        instance.image_url.delete(save=False) # Deletes original image 
        instance.image_url.save(
            original_name,  # using original url name 
            ContentFile(resized_image.getvalue()),
            save=True
        )

    def create(self,validated_data):
        instance = super().create(validated_data)
        self._resize_image(instance)
        return instance

    def update(self, instance, validated_data):
        instance = super().update(instance, validated_data)
        if 'image_url' in validated_data:
            self._resize_image(instance)
=======
=======
>>>>>>> develope
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

<<<<<<< HEAD
>>>>>>> develope
=======
>>>>>>> develope
        return instance


class RatingSerializer(serializers.ModelSerializer):
    score = serializers.DecimalField(
        max_digits=4,
        decimal_places=2,
<<<<<<< HEAD
<<<<<<< HEAD
=======
        # rating consists of 1 to 5 score
>>>>>>> develope
=======
        # rating consists of 1 to 5 score
>>>>>>> develope
        min_value=Decimal('1'),
        max_value=Decimal('5'),
        coerce_to_string=False,
    )
<<<<<<< HEAD
<<<<<<< HEAD
=======
    spot = serializers.PrimaryKeyRelatedField(queryset=Spots.objects.all())
>>>>>>> develope
=======
    spot = serializers.PrimaryKeyRelatedField(queryset=Spots.objects.all())
>>>>>>> develope

    class Meta:
        model = Rating
        fields = "__all__"
<<<<<<< HEAD
<<<<<<< HEAD
        read_only_fields = ['id','created_at','user','spot']
=======
        read_only_fields = ['id','created_at','user']
>>>>>>> develope
=======
        read_only_fields = ['id','created_at','user']
>>>>>>> develope
    
        
        
            
