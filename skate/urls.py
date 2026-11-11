from django.urls import path,include
from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from .routers import router
from rest_framework_simplejwt.views import TokenObtainPairView,TokenRefreshView
from .views import home,RatingViewSet,spot_form,skate_map,feed_page,profile_page
from .geocode.views import GeocodeSearchView
from .tiles import tile
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
    # location search used by the spot form
    path('api/geocode/search/', GeocodeSearchView.as_view(), name='geocode_search'),
    # the map of the skate spots
    path('map/', skate_map, name='skate_map'),
    # the feed of the skate spots
    path('feed/', feed_page, name='feed'),
    # the page of the profile, where the user signs in
    path('profile/', profile_page, name='profile'),
    # the tiles of the map, served by the application
    path('tiles/<path:path>', tile, name='map_tile'),
    # html pages to create and to edit a spot
    path('spots/new/', spot_form, name='spot_create'),
    path('spots/<int:pk>/edit/', spot_form, name='spot_edit'),
    # donwload schema
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    # swagger ui to check endpoints 
    path('api/docs/',SpectacularSwaggerView.as_view(url_name='schema'),
    name='swagger-ui')
 
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)


