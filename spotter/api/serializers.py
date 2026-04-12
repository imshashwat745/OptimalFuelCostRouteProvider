from rest_framework import serializers
from ..core.constants import DEFAULT_BUFFER_GALLONS, DEFAULT_GREEDY_FILL


class RouteQuerySerializer(serializers.Serializer):
    start = serializers.CharField(required=True)
    finish = serializers.CharField(required=True)
    buffer_gallons = serializers.FloatField(
        required=False, default=DEFAULT_BUFFER_GALLONS, min_value=0.0
    )
    greedy_fill = serializers.BooleanField(
        required=False, default=DEFAULT_GREEDY_FILL
    )
