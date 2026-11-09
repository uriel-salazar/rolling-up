from rest_framework.routers import DefaultRouter
from .views import UserViewSet,SpotsViewSet,RatingViewSet
router = DefaultRouter()

router.register(r'users', UserViewSet)
router.register(r'spots',SpotsViewSet)
router.register(r'rating',RatingViewSet)



