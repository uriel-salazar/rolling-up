
from rest_framework.viewsets import ModelViewSet
from rest_framework.parsers import MultiPartParser, FormParser
<<<<<<< HEAD
=======
from rest_framework.generics import RetrieveUpdateAPIView
>>>>>>> develope
from django.shortcuts import render,get_object_or_404
from .models import User,Spots,Rating
from drf_spectacular.utils import extend_schema, OpenApiExample
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly,AllowAny
from .serializers import UserSerializer,SpotSerializer,RatingSerializer
from rest_framework.pagination import LimitOffsetPagination
<<<<<<< HEAD
=======
from .permissions import IsOwnerOrReadOnly
>>>>>>> develope


def home(request):
    return render(request,'basic_home.html')


class UserViewSet(ModelViewSet):
    """ User must be authenticated to get http methods like 
    put and delete.
    Includes functions like get_permissions() to check for authenticity. 
    With pagination included
    """
    queryset = User.objects.all()
    serializer_class = UserSerializer
    pagination_class = LimitOffsetPagination
<<<<<<< HEAD
=======
    permission_classes = [IsAuthenticatedOrReadOnly]

>>>>>>> develope
    
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
<<<<<<< HEAD
        if self.action == 'create': # If it's post 
             return [AllowAny()]
        return [IsAuthenticatedOrReadOnly()]
    
    
    
class SpotsViewSet(ModelViewSet):
    
    permission_classes = [IsAuthenticated]
    
=======
        if self.action == 'create':
            return [AllowAny()]
        return [IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return User.objects.none()
        if user.is_staff:
            return User.objects.all()
        return User.objects.filter(pk=user.pk)
    
    
class SpotsViewSet(ModelViewSet):

    permission_classes = [IsAuthenticatedOrReadOnly,IsOwnerOrReadOnly]

>>>>>>> develope
    queryset= Spots.objects.all()
    pagination_class = LimitOffsetPagination
    parser_classes = (MultiPartParser, FormParser)
    serializer_class= SpotSerializer
<<<<<<< HEAD
    

    def perform_create(self, serializer):
        """ Injects to current user before saving it."""
    
=======

    def perform_create(self, serializer):
        """ Injects to current user before saving it."""

>>>>>>> develope
        serializer.save(user=self.request.user)
    
class RatingViewSet(ModelViewSet):
    
    serializer_class = RatingSerializer
    mini_serializer_class= RatingSerializer
    queryset = Rating.objects.all()
    pagination_class = LimitOffsetPagination
<<<<<<< HEAD
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
=======
    permission_classes = [IsAuthenticated,IsOwnerOrReadOnly]
    
    def perform_create(self, serializer):
        spot_id = self.kwargs.get('spots_id')

        extra = {'user': self.request.user}
        if spot_id:
            extra['spot'] = get_object_or_404(Spots, pk=spot_id)

        serializer.save(**extra)
>>>>>>> develope

    