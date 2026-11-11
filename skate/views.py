
import logging

from rest_framework.viewsets import ModelViewSet
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.generics import RetrieveUpdateAPIView
from django.shortcuts import render,get_object_or_404
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db.models import Avg, Count, Q
from django.utils.safestring import mark_safe
from .models import User,Spots,Rating
from drf_spectacular.utils import extend_schema, OpenApiExample
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly,AllowAny
from .serializers import UserSerializer,SpotSerializer,RatingSerializer
from rest_framework.pagination import LimitOffsetPagination
from .permissions import IsOwnerOrReadOnly

logger = logging.getLogger(__name__)

# The raster tiles of CARTO are only available up to this zoom level.
CARTO_MAX_ZOOM = 18


def home(request):
    return render(request,'basic_home.html')


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
        },
    )


def feed_page(request):
    """ Render the feed of the skate spots.

        The page is public, the spots are read from the public API
        without an account.
    """
    return render(request, 'feed.html')


def profile_page(request):
    """ Render the page of the profile, where the user signs in.

        The page is public, signing in happens through the API.
    """
    return render(request, 'profile.html')


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
        )

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

    