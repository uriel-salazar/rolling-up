from django.urls import path,include
from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from .routers import router
from rest_framework_simplejwt.views import TokenObtainPairView,TokenRefreshView
from .views import home,RatingViewSet
from drf_spectacular.views import  SpectacularAPIView,SpectacularSwaggerView



urlpatterns = [
    path('',home), # html of home 
    path(settings.ADMIN_URL, admin.site.urls),
    # get token 
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    #refresh token url 
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
 
    # paths from router 
    path('api/',include(router.urls)),
    #path to get rating from id of spot 
    path('api/spots/<int:spots_id>/rating/',RatingViewSet.as_view({"post":"create"})),
    # donwload schema
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    # swagger ui to check endpoints 
    path('api/docs/',SpectacularSwaggerView.as_view(url_name='schema'),
    name='swagger-ui')
     
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)


