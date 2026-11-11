from django.urls import path,include
from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from .routers import router
from rest_framework_simplejwt.views import TokenObtainPairView,TokenRefreshView
from .views import home,RatingViewSet,spot_form,skate_map,feed_page,profile_page,register_page,google_login,google_callback,SpotPhotoViewSet,spot_detail_page
from .geocode.views import GeocodeSearchView
from .discovery.views import NearbySkateparksView, ViewportSkateparksView
from .google_places.views import GooglePlacePhotoView
from .tiles import tile
from drf_spectacular.views import  SpectacularAPIView,SpectacularSwaggerView



urlpatterns = [
    path('',home), # html of home
    path(settings.ADMIN_URL, admin.site.urls),
    # get token 
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    #refresh token url 
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
 
    # live OSM discoveries, separate from the registered spots
    path(
        'api/spots/nearby/',
        NearbySkateparksView.as_view(),
        name='nearby_skateparks',
    ),
    path(
        'api/spots/viewport/',
        ViewportSkateparksView.as_view(),
        name='viewport_skateparks',
    ),
    # paths from router 
    path('api/',include(router.urls)),
    #path to get rating from id of spot 
    path('api/spots/<int:spots_id>/rating/',RatingViewSet.as_view({"post":"create"})),
    # the ratings of one spot, read by everybody
    path('api/spots/<int:spot_id>/ratings/', RatingViewSet.as_view({"get":"list"}), name='spot_ratings'),
    # the same endpoint, with the name used by the interface
    path('api/spots/<int:spots_id>/rate/', RatingViewSet.as_view({"post":"create"}), name='spot_rate'),
    # additional photographs for a spot (OSM or community) — no duplicates, just more photos
    path('api/spots/<int:spot_id>/photos/', SpotPhotoViewSet.as_view({'get':'list','post':'create'}), name='spot_photos'),
    path('api/spots/<int:spot_id>/photos/<int:pk>/', SpotPhotoViewSet.as_view({'get':'retrieve','put':'update','patch':'partial_update','delete':'destroy'}), name='spot_photo_detail'),
    # location search used by the spot form
    path('api/geocode/search/', GeocodeSearchView.as_view(), name='geocode_search'),
    # the map of the skate spots
    path('map/', skate_map, name='skate_map'),
    # the feed of the skate spots
    path('feed/', feed_page, name='feed'),
    # the page of the profile, where the user signs in
    path('profile/', profile_page, name='profile'),
    # the page where a new account is created
    path('register/', register_page, name='register'),
    # Google OAuth login
    path('auth/google/login/', google_login, name='google_login'),
    path('auth/google/callback/', google_callback, name='google_callback'),
    # the tiles of the map, served by the application
    path('tiles/<path:path>', tile, name='map_tile'),
    # photographs of the Google Places skateparks, served without the key
    path(
        'api/places/photo/<path:photo_name>',
        GooglePlacePhotoView.as_view(),
        name='google_place_photo',
    ),
    path(
        'api/places/photo/',
        GooglePlacePhotoView.as_view(),
        name='google_place_photo_query',
    ),
    # html pages to create and to edit a spot
    path('spots/new/', spot_form, name='spot_create'),
    path('spots/<int:pk>/edit/', spot_form, name='spot_edit'),
    path('spots/<int:pk>/', spot_detail_page, name='spot_detail'),
    # donwload schema
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    # swagger ui to check endpoints 
    path('api/docs/',SpectacularSwaggerView.as_view(url_name='schema'),
    name='swagger-ui')
 
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)


