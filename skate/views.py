
from rest_framework.viewsets import ModelViewSet
from rest_framework.parsers import MultiPartParser, FormParser
from django.shortcuts import render,get_object_or_404
from .models import User,Spots,Rating
from drf_spectacular.utils import extend_schema, OpenApiExample
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly,AllowAny
from .serializers import UserSerializer,SpotSerializer,RatingSerializer
from rest_framework.pagination import LimitOffsetPagination


def home(request):
    return render(request,'basic_home.html')


class UserViewSet(ModelViewSet):
    """ User must be authenticated to get http methods like 
    post or delete. 
    """
    queryset = User.objects.all()
    serializer_class = UserSerializer
    pagination_class = LimitOffsetPagination
    
    @extend_schema(
        request=UserSerializer,
        examples=[
            OpenApiExample(
                "Create user example",
                value={
                    "username": "robert86",
                    "email": "robert@gmail.com",
                    "password": "a_secure_password"
                },
                request_only=True,
            )
        ],
    ) 
    def create(self, request, *args, **kwargs):
        """Function to attach it to decorator"""
        return super().create(request, *args, **kwargs)

    def get_permissions(self):
        """ Anybody can create an user but you still have
        to get authenticated to get acces to more https methods 
        like put or delete. """
        if self.action == 'create': # If it's post 
             return [AllowAny()]
        return [IsAuthenticatedOrReadOnly()]
    
    
    
class SpotsViewSet(ModelViewSet):
    
    permission_classes = [IsAuthenticated]
    
    queryset= Spots.objects.all()
    pagination_class = LimitOffsetPagination
    parser_classes = (MultiPartParser, FormParser)
    serializer_class= SpotSerializer
    

    def perform_create(self, serializer):
        """ Injects to current user before saving it."""
    
        serializer.save(user=self.request.user)
    
class RatingViewSet(ModelViewSet):
    
    serializer_class = RatingSerializer
    mini_serializer_class= RatingSerializer
    queryset = Rating.objects.all()
    pagination_class = LimitOffsetPagination
    permission_classes = [IsAuthenticated]
    
    def perform_create(self, serializer):
        spot = get_object_or_404(
                Spots,
                pk=self.kwargs['spots_id']
            )

        serializer.save(
                user=self.request.user,
                spot=spot
            )

    