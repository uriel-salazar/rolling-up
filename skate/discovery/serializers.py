"""Serializers for live OpenStreetMap discoveries."""

from __future__ import annotations

from rest_framework import serializers


class ExternalSpotSerializer(serializers.Serializer):
    """A skatepark found live in OpenStreetMap, not stored in the database."""

    id = serializers.CharField()
    external = serializers.BooleanField()
    name_spot = serializers.CharField()
    body = serializers.CharField(allow_null=True, allow_blank=True)
    latitude = serializers.FloatField()
    longitude = serializers.FloatField()
    category = serializers.CharField()
    source = serializers.CharField()
    osm_id = serializers.IntegerField()
    osm_type = serializers.CharField()
    osm_metadata = serializers.JSONField()
    image_url = serializers.CharField(allow_null=True, allow_blank=True)
    image_attribution = serializers.CharField(allow_null=True, allow_blank=True)
    image_license = serializers.CharField(allow_null=True, allow_blank=True)
    image_license_url = serializers.CharField(allow_null=True, allow_blank=True)
    image_source = serializers.CharField(allow_null=True, allow_blank=True)
    address = serializers.CharField(allow_blank=True)
    rating = serializers.FloatField(allow_null=True)
    rating_count = serializers.IntegerField()


class DiscoveryAreaSerializer(serializers.Serializer):
    """The geographic area a discovery request covered."""

    type = serializers.CharField()
    south = serializers.FloatField(required=False)
    west = serializers.FloatField(required=False)
    north = serializers.FloatField(required=False)
    east = serializers.FloatField(required=False)
    latitude = serializers.FloatField(required=False)
    longitude = serializers.FloatField(required=False)
    radius = serializers.FloatField(required=False)


class DiscoveryResponseSerializer(serializers.Serializer):
    """The stable answer of a nearby or viewport discovery."""

    source = serializers.CharField()
    count = serializers.IntegerField()
    results = ExternalSpotSerializer(many=True)
    area = DiscoveryAreaSerializer()
    cached = serializers.BooleanField()
    stale = serializers.BooleanField()
    attribution = serializers.CharField()


class DiscoveryErrorSerializer(serializers.Serializer):
    """The answer of a discovery request that could not be completed."""

    detail = serializers.CharField()
    results = serializers.ListField(child=serializers.DictField(), default=list)
