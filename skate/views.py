
import logging
import os

import requests
from django.http import HttpResponseRedirect
from django.shortcuts import render,get_object_or_404
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db.models import Avg, Count, Q, Case, When, IntegerField
from django.utils.safestring import mark_safe
from django.views.decorators.clickjacking import xframe_options_sameorigin
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.viewsets import ModelViewSet
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.generics import RetrieveUpdateAPIView
from . import google_auth
from .models import User,Spots,Rating,SpotPhoto
from drf_spectacular.utils import extend_schema, OpenApiExample
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly,AllowAny
from .serializers import UserSerializer,SpotSerializer,RatingSerializer,SpotPhotoSerializer
from rest_framework.pagination import LimitOffsetPagination
from .permissions import IsOwnerOrReadOnly, IsUploaderOrReadOnly
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action

logger = logging.getLogger(__name__)

# The raster tiles of CARTO are only available up to this zoom level.
CARTO_MAX_ZOOM = 18


def home(request):
    return render(request,'basic_home.html')


@xframe_options_sameorigin
def skate_map(request):
    """ Render the map of the skate spots.

        The page is public, the spots are read from the public API
        without an account.
    """
    return render(
        request,
        'map.html',
        {
            'tile_config': build_tile_config(),
            'default_center': settings.MAP_DEFAULT_CENTER,
            'default_zoom': settings.MAP_DEFAULT_ZOOM,
            'embed': request.GET.get('embed') == '1',
        },
    )


@xframe_options_sameorigin
def feed_page(request):
    """ Render the feed of the skate spots.

        The page is public, the spots are read from the public API
        without an account.
    """
    return render(
        request,
        'feed.html',
        {'embed': request.GET.get('embed') == '1'},
    )


def profile_page(request):
    """ Render the page of the profile, where the user signs in.

        The page is public, signing in happens through the API.
    """
    return render(request, 'profile.html')


def spot_detail_page(request, pk):
    """ Render the detail page of a skate spot.

        The page is public: the spot itself, its photos and its rating
        are read from the API. Uploading a photo or rating the spot
        requires being logged in.
    """
    spot = get_object_or_404(Spots, pk=pk)
    tile_config = build_tile_config()

    # Resolve the main image through the same pipeline the API uses.
    from skate.media_api.images_skateparks.resolver import resolve_spot_image
    resolved = resolve_spot_image(spot, request)
    main_image = resolved.get('url') if resolved else None

    # Additional photos uploaded by users.
    photos = SpotPhoto.objects.filter(spot=spot).select_related('uploaded_by')
    additional_photos = [
        {
            'id': photo.id,
            'image_url': photo.image.url if photo.image else None,
            'caption': photo.caption,
            'uploaded_by_username': photo.uploaded_by.username,
        }
        for photo in photos
    ]

    # Average rating and count.
    stats = spot.rating_set.aggregate(
        average=Avg('score'),
        count=Count('id'),
    )
    average_rating = stats['average']
    rating_count = stats['count']

    # The current user's rating, if authenticated.
    user_rating = None
    if request.user.is_authenticated:
        try:
            user_rating = Rating.objects.get(spot=spot, user=request.user)
        except Rating.DoesNotExist:
            pass

    return render(
        request,
        'spot_detail.html',
        {
            'spot': spot,
            'main_image': main_image,
            'additional_photos': additional_photos,
            'average_rating': average_rating,
            'rating_count': rating_count,
            'user_rating': user_rating,
            'tile_config': tile_config,
        },
    )


def register_page(request):
    """ Render the registration page.

        The page is public, account creation happens through the API.
    """
    return render(request, 'register.html')


def google_login(request):
    """ Initiate the Google OAuth2 flow.

        Redirects the browser to Google's consent screen. A random
        ``state`` is stored in the session so the callback can reject a
        forged or replayed request. After the user approves, Google
        calls back at /auth/google/callback/.
    """
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        return HttpResponseRedirect("/profile/?error=google_not_configured")

    state = google_auth.generate_state()
    request.session["google_oauth_state"] = state
    request.session.modified = True
    return HttpResponseRedirect(google_auth.build_authorization_url(state))


def google_callback(request):
    """ Handle the Google OAuth2 callback.

        Validates the ``state``, verifies Google's ID token (signature,
        audience, expiration and verified email), finds or creates the
        local user by email and issues the same JWT the normal login
        issues.
    """
    error = request.GET.get("error")
    if error:
        return HttpResponseRedirect(f"/profile/?error=google_{error}")

    code = request.GET.get("code")
    if not code:
        return HttpResponseRedirect("/profile/?error=google_no_code")

    expected_state = request.session.pop("google_oauth_state", None)
    if not google_auth.validate_state(request.GET.get("state"), expected_state):
        logger.warning("Google login rejected: invalid state")
        return HttpResponseRedirect("/profile/?error=google_state_invalid")

    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        return HttpResponseRedirect("/profile/?error=google_not_configured")

    try:
        user = google_auth.authenticate_with_google(code)
    except google_auth.GoogleAuthError as error:
        logger.warning("Google login failed: %s", error.code)
        return HttpResponseRedirect(f"/profile/?error={error.code}")
    except requests.RequestException:
        logger.warning("Google login request failed", exc_info=True)
        return HttpResponseRedirect("/profile/?error=google_network_error")

    refresh = RefreshToken.for_user(user)
    return HttpResponseRedirect(
        f"/profile/?access={str(refresh.access_token)}"
        f"&refresh={str(refresh)}&google=1"
    )


def build_tile_config():
    """Return the configuration of the tile layer of the map.

    The provider is a setting, so it can be changed without a new
    release, which is what the usage policies ask for. The attribution
    is built here because every provider has its own rules:

    * the standard OpenStreetMap tiles need the credit of
      OpenStreetMap, a link to report a problem with the map and a
      way to contact the operator,
    * the CARTO basemaps need the credit of **both** OpenStreetMap and
      CARTO, and they need an API key.

    When the provider needs a key the tiles go through the proxy of the
    application, so the key never reaches the browser.

    The links use single quotes on purpose: the string is rendered
    inside a double quoted HTML attribute and it is not escaped.
    """
    url = settings.OSM_TILE_URL
    is_carto = 'cartocdn' in url
    subdomains = settings.OSM_TILE_SUBDOMAINS

    max_zoom = settings.OSM_TILE_MAX_ZOOM
    if is_carto and max_zoom > CARTO_MAX_ZOOM:
        # The raster tiles of CARTO only go up to zoom 18. A bigger
        # value makes the server answer "Forbidden" and the map shows
        # empty tiles instead of the streets.
        logger.warning(
            "OSM_TILE_MAX_ZOOM is %s but the CARTO raster tiles only go up "
            "to %s, it is lowered.",
            max_zoom,
            CARTO_MAX_ZOOM,
        )
        max_zoom = CARTO_MAX_ZOOM

    attribution = (
        "&copy; <a href='https://www.openstreetmap.org/copyright' "
        "target='_blank' rel='noopener'>OpenStreetMap</a> contributors"
        " &middot; <a href='https://www.openstreetmap.org/fixthemap' "
        "target='_blank' rel='noopener'>Report a map issue</a>"
    )

    if is_carto:
        # CARTO asks for the credit of both projects, both linked.
        attribution += (
            " &middot; <a href='https://carto.com/attribution/' "
            "target='_blank' rel='noopener'>CARTO</a>"
        )

        if not settings.OSM_TILE_API_KEY:
            logger.warning(
                "The CARTO basemaps need an API key, the map will show a "
                "placeholder until OSM_TILE_API_KEY is set. "
                "https://carto.com/basemaps/apikey/"
            )
        else:
            # The key is a credential, the tiles go through the proxy
            # of the application so it never reaches the browser.
            url = settings.TILE_PROXY_PATH
            subdomains = ''
    else:
        # The standard tiles need no key, the browser can ask for them
        # directly and the server does not have to serve them.
        pass

    attribution += (
        f" &middot; <a href='mailto:{settings.OSM_CONTACT_EMAIL}'>"
        f"{settings.OSM_CONTACT_EMAIL}</a>"
    )

    options = {
        'url': url,
        'max_zoom': max_zoom,
        'subdomains': subdomains,
        'attribution': mark_safe(attribution),
        'provider': 'carto' if is_carto else 'osm',
        # CARTO answers without a key with a placeholder that says
        # "API KEY REQUIRED", so the map has to say it is not ready.
        'key_missing': is_carto and not settings.OSM_TILE_API_KEY,
    }

    return options


@xframe_options_sameorigin
def spot_form(request, pk=None):
    """ Render the form used to create or to edit a skate spot.

        The page itself is public: the application logs the users in
        with a JWT that the browser keeps in the local storage, so the
        server can not tell who is visiting. The API is what protects
        the spots, it refuses a write from somebody who is not
        authenticated and a write on a spot of somebody else.

        When the visitor does have a Django session the ownership is
        checked right away.
    """
    spot = None
    if pk is not None:
        spot = get_object_or_404(Spots, pk=pk)

    if (
        spot is not None
        and request.user.is_authenticated
        and spot.user_id != request.user.id
    ):
        raise PermissionDenied("You can only edit your own spots.")

    tile_config = build_tile_config()

    return render(
        request,
        'spot_form.html',
        {
            'spot': spot,
            'is_edit': pk is not None,
            'tile_config': tile_config,
            'embed': request.GET.get('embed') == '1',
        },
    )


class UserViewSet(ModelViewSet):
    """ User must be authenticated to get http methods like 
    put and delete.
    Includes functions like get_permissions() to check for authenticity. 
    With pagination included
    """
    queryset = User.objects.all()
    serializer_class = UserSerializer
    pagination_class = LimitOffsetPagination
    permission_classes = [IsOwnerOrReadOnly]

    
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

    queryset= Spots.objects.all()
    pagination_class = LimitOffsetPagination
    # Multipart is kept for the image upload. JSON is accepted as well,
    # so a client that does not upload a picture can send the
    # coordinates with a null to remove the location of a spot.
    parser_classes = (MultiPartParser, FormParser, JSONParser)
    serializer_class= SpotSerializer

    def get_queryset(self):
        """Return the spots, filtered and with their ratings.

        The parameters are all optional, so the endpoint answers the
        same as before when none of them is used:

        * ``search``   -- a text that is looked for in the name and in
          the description of the spot,
        * ``category`` -- ``skatepark``, ``street`` or ``diy``,
        * ``source``   -- ``osm`` or ``community``.
        """
        queryset = Spots.objects.annotate(
            average_rating=Avg('rating__score'),
            rating_count=Count('rating', distinct=True),
            has_image=Case(
                When(image_url__isnull=False, then=1),
                When(google_metadata__has_key='photos', then=1),
                When(osm_metadata__has_key='image', then=1),
                default=0,
                output_field=IntegerField(),
            ),
        ).order_by('-has_image', 'name_spot')

        params = self.request.query_params

        search = (params.get('search') or '').strip()
        if search:
            queryset = queryset.filter(
                Q(name_spot__icontains=search) | Q(body__icontains=search)
            )

        category = (params.get('category') or '').strip()
        if category and category in Spots.CATEGORY_VALUES:
            queryset = queryset.filter(category=category)

        source = (params.get('source') or '').strip()
        if source and source in Spots.SOURCE_VALUES:
            queryset = queryset.filter(source=source)

        return queryset

    def perform_create(self, serializer):
        """ Injects to current user before saving it."""

        serializer.save(user=self.request.user)
    
class RatingViewSet(ModelViewSet):
    
    serializer_class = RatingSerializer
    mini_serializer_class= RatingSerializer
    queryset = Rating.objects.all()
    pagination_class = LimitOffsetPagination
    permission_classes = [IsAuthenticated,IsOwnerOrReadOnly]
    
    def perform_create(self, serializer):
        spot = get_object_or_404(
                Spots,
                pk=self.kwargs['spots_id']
            )

        serializer.save(
                user=self.request.user,
                spot=spot
            )


class SpotPhotoViewSet(viewsets.ModelViewSet):
    """ Additional photographs for a skate spot.

        Users can attach several extra photos to any spot (including
        OpenStreetMap imported ones). The uploader is recorded so only
        the owner can delete their own photos.
    """
    serializer_class = SpotPhotoSerializer
    pagination_class = LimitOffsetPagination

    def get_queryset(self):
        spot_id = self.kwargs.get('spot_id')
        if spot_id:
            return SpotPhoto.objects.filter(spot_id=spot_id)
        return SpotPhoto.objects.none()

    def get_permissions(self):
        if self.action == 'create':
            return [IsAuthenticated()]
        if self.action in ('update', 'partial_update', 'destroy'):
            return [IsAuthenticated(), IsUploaderOrReadOnly()]
        return [AllowAny()]

    def perform_create(self, serializer):
        spot = get_object_or_404(Spots, pk=self.kwargs['spot_id'])
        serializer.save(spot=spot, uploaded_by=self.request.user)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context

    