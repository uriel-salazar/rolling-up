"""Serializers describing the answer of the geocoding endpoint."""

from __future__ import annotations

from rest_framework import serializers


class GeocodeResultSerializer(serializers.Serializer):
    """One place returned by the geocoding service."""

    label = serializers.CharField(
        help_text='The full description of the place.'
    )
    short_label = serializers.CharField(
        help_text='The name of the place, without the rest of the address.'
    )
    latitude = serializers.FloatField()
    longitude = serializers.FloatField()
    category = serializers.CharField(
        allow_blank=True, help_text='The category of the place, for example leisure.'
    )
    type = serializers.CharField(
        allow_blank=True, help_text='The type of the place, for example skatepark.'
    )
    osm_id = serializers.CharField(
        allow_null=True, help_text='The id of the OpenStreetMap object.'
    )
    osm_type = serializers.CharField(
        allow_blank=True, help_text='The type of the OpenStreetMap object.'
    )


class GeocodeSearchResponseSerializer(serializers.Serializer):
    """The answer of a location search."""

    query = serializers.CharField()
    count = serializers.IntegerField()
    results = GeocodeResultSerializer(many=True)


class GeocodeErrorSerializer(serializers.Serializer):
    """The answer of a failed location search."""

    detail = serializers.CharField()
    results = serializers.ListField(child=serializers.DictField(), default=list)
