from rest_framework import serializers


class RouteRequestSerializer(serializers.Serializer):
    start = serializers.CharField(
        required=True,
        help_text="Starting location in the USA (e.g., 'New York, NY')"
    )
    finish = serializers.CharField(
        required=True,
        help_text="Finish location in the USA (e.g., 'Los Angeles, CA')"
    )


class FuelStopSerializer(serializers.Serializer):
    truckstop_id = serializers.CharField()
    name = serializers.CharField()
    address = serializers.CharField()
    city = serializers.CharField()
    state = serializers.CharField()
    latitude = serializers.FloatField()
    longitude = serializers.FloatField()
    price_per_gallon = serializers.FloatField()
    mile_marker = serializers.FloatField()
    gallons_purchased = serializers.FloatField()
    cost = serializers.FloatField()
