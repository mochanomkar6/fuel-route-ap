import hashlib
import logging
import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

ORS_GEOCODE_URL = "https://api.openrouteservice.org/geocode/search"
ORS_DIRECTIONS_URL = "https://api.openrouteservice.org/v2/directions/driving-car/geojson"
METERS_TO_MILES = 0.000621371


class MapService:
    def __init__(self):
        self.api_key = getattr(settings, 'ORS_API_KEY', '')

    def geocode(self, location_str):
        """
        Geocodes a location string (e.g. 'New York, NY') into (lon, lat) within the USA.
        Results are cached to avoid repeated calls.
        """
        cache_key = f"geocode_{hashlib.md5(location_str.lower().strip().encode()).hexdigest()}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        headers = {
            "Authorization": self.api_key,
            "Accept": "application/json, application/geo+json, application/gpx+xml, img/png; charset=utf-8",
        }
        params = {
            "api_key": self.api_key,
            "text": location_str,
            "boundary.country": "USA",
            "size": 1
        }

        response = requests.get(ORS_GEOCODE_URL, headers=headers, params=params, timeout=10)
        if response.status_code != 200:
            raise ValueError(f"Failed to geocode '{location_str}': {response.text}")

        data = response.json()
        features = data.get("features", [])
        if not features:
            raise ValueError(f"Location not found: '{location_str}'")

        # GeoJSON coordinates are in [longitude, latitude] format
        coordinates = features[0]["geometry"]["coordinates"]
        lon, lat = coordinates[0], coordinates[1]
        
        cache.set(cache_key, (lon, lat), timeout=86400 * 7)  # Cache for 7 days
        return lon, lat

    def get_route(self, start_str, end_str):
        """
        Fetches the complete driving route between start and end.
        Returns:
            - total_distance_miles: float
            - duration_seconds: float
            - coordinates: list of [lon, lat] points
            - geojson: complete GeoJSON Feature for mapping
        """
        # Resolve start and end coordinates
        start_lon, start_lat = self.geocode(start_str)
        end_lon, end_lat = self.geocode(end_str)

        # Check route cache
        route_cache_key = f"route_{start_lon}_{start_lat}_{end_lon}_{end_lat}"
        cached_route = cache.get(route_cache_key)
        if cached_route:
            logger.info("Serving route from in-memory cache.")
            return cached_route

        # Single POST request to OpenRouteService Directions API
        headers = {
            "Authorization": self.api_key,
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json, application/geo+json"
        }
        body = {
            "coordinates": [
                [start_lon, start_lat],
                [end_lon, end_lat]
            ],
            "units": "m",
            "geometry": True
        }

        response = requests.post(ORS_DIRECTIONS_URL, json=body, headers=headers, timeout=15)
        if response.status_code != 200:
            raise ValueError(f"OpenRouteService directions error ({response.status_code}): {response.text}")

        geojson_data = response.json()
        feature = geojson_data["features"][0]
        properties = feature["properties"]["summary"]
        geometry = feature["geometry"]

        total_distance_meters = properties["distance"]
        total_distance_miles = round(total_distance_meters * METERS_TO_MILES, 2)
        duration_seconds = properties["duration"]
        route_coords = geometry["coordinates"]  # List of [lon, lat]

        result = {
            "start": {"name": start_str, "lat": start_lat, "lon": start_lon},
            "finish": {"name": end_str, "lat": end_lat, "lon": end_lon},
            "total_distance_miles": total_distance_miles,
            "duration_seconds": duration_seconds,
            "coordinates": route_coords,
            "geojson": feature
        }

        # Cache route for 24 hours
        cache.set(route_cache_key, result, timeout=86400)
        return result
