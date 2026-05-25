from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings
class User(AbstractUser):
    first_name = None
    last_name = None
    username=models.CharField(max_length=25,unique=True)
    email = models.EmailField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    
    def __str__(self):
        return self.username
    

class Spots(models.Model):
    name_spot = models.CharField(max_length = 200)
    body = models.TextField( null= True,max_length=1000)
    image_url=models.ImageField(null=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete = models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.name_spot
    

class Rating(models.Model):
    score = models.DecimalField(max_digits=4,decimal_places=2)
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    spot = models.ForeignKey(Spots, on_delete=models.CASCADE)
    
    created_at = models.DateTimeField(auto_now_add = True)
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'spot'],
                name='unique_user_spot_rating'
            )
        ]
        

    def __str__(self):
        return f"{self.user} rated {self.spot} - {self.score}"
    
    
   

    