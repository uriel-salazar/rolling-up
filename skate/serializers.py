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
    
    password = serializers.CharField(write_only=True) 
    #only user can see their password.
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
        user = User(
            username=validated_data['username'],
            email=validated_data['email'],
        )
        user.set_password(validated_data['password'])  
        user.save()
        return user
    
    def words_username(self, username):
        """ 
        Username must have at least 5 words. 

        Raises:
            serializers.ValidationError: validation if the username is less 
            than 5 words 

        Returns:
            username
        """
        if len(username.split()) < 5:
            raise serializers.ValidationError(f"'{username}' must have at least 5 words.")
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
        
    def create(self,validated_data):
        instance = super().create(validated_data)
        original_name = instance.image_url.name
        
        if instance.image_url:
            #function that resizes image 
            resized_image = image_logic.image_resize_800(instance.image_url)
    
            instance.image_url.delete(save=False) # Deletes original image 
            instance.image_url.save(
            original_name,  # using original url name 
            ContentFile(resized_image.getvalue()),
            save=True
        )

        return instance
            
            
class RatingSerializer(serializers.ModelSerializer):
        class Meta:
            model = Rating
            fields = "__all__"
            read_only_fields = ['id','created_at','user','spot']
        
        # Return it as decimal 
        def get_score(self,column):
            return Decimal(column.score)
        
    
        
        
            
