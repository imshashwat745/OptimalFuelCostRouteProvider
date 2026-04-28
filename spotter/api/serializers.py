from rest_framework import serializers
from ..core.constants import DEFAULT_BUFFER_GALLONS, DEFAULT_GREEDY_FILL


class RouteQuerySerializer(serializers.Serializer):
    start_address = serializers.CharField(required=True)
    destination_address = serializers.CharField(required=True)
    buffer_gallons = serializers.FloatField(
        required=False, default=DEFAULT_BUFFER_GALLONS, min_value=0.0
    )
    greedy_fill = serializers.BooleanField(
        required=False, default=DEFAULT_GREEDY_FILL
    )
