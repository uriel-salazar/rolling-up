from django.db import models
from django.db.models import Q
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
    """ A skate spot.

        Spots come from two origins:

        * ``community`` -- submitted by a registered user through the API.
        * ``osm``       -- imported from OpenStreetMap by the
          ``import_osm_skateparks`` management command.

        The ``osm_type`` / ``osm_id`` pair identifies the original OSM
        object and is unique, so running the importer twice never creates
        duplicates.
    """

    SOURCE_COMMUNITY = 'community'
    SOURCE_OSM = 'osm'
    SOURCE_CHOICES = [
        (SOURCE_COMMUNITY, 'Community'),
        (SOURCE_OSM, 'OpenStreetMap'),
    ]

    OSM_TYPE_NODE = 'node'
    OSM_TYPE_WAY = 'way'
    OSM_TYPE_RELATION = 'relation'
    OSM_TYPE_CHOICES = [
        (OSM_TYPE_NODE, 'Node'),
        (OSM_TYPE_WAY, 'Way'),
        (OSM_TYPE_RELATION, 'Relation'),
    ]

    # The kind of spot. A skatepark is a built place, a street spot is
    # a spot in the street and a DIY spot is a homemade one.
    CATEGORY_SKATEPARK = 'skatepark'
    CATEGORY_STREET = 'street'
    CATEGORY_DIY = 'diy'
    CATEGORY_CHOICES = [
        (CATEGORY_SKATEPARK, 'Skatepark'),
        (CATEGORY_STREET, 'Street spot'),
        (CATEGORY_DIY, 'DIY spot'),
    ]

    name_spot = models.CharField(max_length = 200)
    body = models.TextField( null= True,max_length=1000)
    image_url=models.ImageField(null=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete = models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    # The kind of spot. The importer fills it from the OpenStreetMap
    # tags and the users pick it when they publish a spot.
    category = models.CharField(
        max_length=16,
        choices=CATEGORY_CHOICES,
        default=CATEGORY_STREET,
    )

    # Geographic coordinates. Plain decimals are used on purpose: the
    # project runs on PostgreSQL without PostGIS, and Phase 1 only needs
    # to persist the position of an imported skatepark.
    latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )
    longitude = models.DecimalField(
        max_digits=10, decimal_places=6, null=True, blank=True
    )

    # Provenance of the record.
    source = models.CharField(
        max_length=16, choices=SOURCE_CHOICES, default=SOURCE_COMMUNITY
    )
    osm_id = models.BigIntegerField(null=True, blank=True)
    osm_type = models.CharField(
        max_length=16, choices=OSM_TYPE_CHOICES, null=True, blank=True
    )
    osm_metadata = models.JSONField(null=True, blank=True)

    class Meta:
        constraints = [
            # Partial unique index: only OSM records carry osm_id, so
            # community spots (NULL) are never affected.
            models.UniqueConstraint(
                fields=['osm_type', 'osm_id'],
                name='unique_osm_object',
                condition=Q(osm_id__isnull=False),
            ),
        ]

    def __str__(self):
        return self.name_spot

    # The values the filters accept, used to ignore a wrong one.
    SOURCE_VALUES = [value for value, _ in SOURCE_CHOICES]
    CATEGORY_VALUES = [value for value, _ in CATEGORY_CHOICES]

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
    
    
   

    