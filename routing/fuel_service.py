import os
import math
import logging
import pandas as pd
import numpy as np
from pathlib import Path
from scipy.spatial import KDTree
from django.conf import settings

logger = logging.getLogger(__name__)

EARTH_RADIUS_MILES = 3958.8


def lat_lon_to_cartesian(lat_deg, lon_deg):
    """
    Converts latitude and longitude (degrees) to 3D Cartesian coordinates (x, y, z)
    on a sphere of unit radius. This allows accurate Euclidean distance querying with KDTree.
    """
    lat_rad = np.radians(lat_deg)
    lon_rad = np.radians(lon_deg)
    x = np.cos(lat_rad) * np.cos(lon_rad)
    y = np.cos(lat_rad) * np.sin(lon_rad)
    z = np.sin(lat_rad)
    return np.column_stack((x, y, z))


class FuelService:
    _instance = None
    _df = None
    _tree = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        """Loads and pre-processes the fuel stops dataset with coordinates."""
        csv_path = settings.FUEL_PRICES_PATH
        cache_path = settings.BASE_DIR / 'fuel_stops_with_coords.csv'

        if cache_path.exists():
            self._df = pd.read_csv(cache_path)
        else:
            self._df = self._enrich_coordinates(csv_path, cache_path)

        # Drop any records without valid coordinates or price
        self._df = self._df.dropna(subset=['latitude', 'longitude', 'Retail Price']).copy()
        self._df['Retail Price'] = pd.to_numeric(self._df['Retail Price'], errors='coerce')
        self._df = self._df.dropna(subset=['Retail Price']).reset_index(drop=True)

        # Build KDTree for sub-millisecond spatial proximity search
        cartesian_coords = lat_lon_to_cartesian(
            self._df['latitude'].values,
            self._df['longitude'].values
        )
        self._tree = KDTree(cartesian_coords)
        logger.info(f"Loaded {len(self._df)} fuel stops with KDTree index.")

    def _enrich_coordinates(self, raw_csv_path, output_csv_path):
        """
        Merges raw fuel stops with standard US city coordinates
        so zero runtime geocoding calls are required.
        """
        df_fuel = pd.read_csv(raw_csv_path)
        df_fuel['city_clean'] = df_fuel['City'].astype(str).str.strip().str.upper()
        df_fuel['state_clean'] = df_fuel['State'].astype(str).str.strip().str.upper()

        # Download open US cities coordinates dataset once
        us_cities_url = 'https://raw.githubusercontent.com/kelvins/US-Cities-Database/main/csv/us_cities.csv'
        try:
            df_cities = pd.read_csv(us_cities_url)
            df_cities['city_clean'] = df_cities['CITY'].astype(str).str.strip().str.upper()
            df_cities['state_clean'] = df_cities['STATE_CODE'].astype(str).str.strip().str.upper()
            cities_coords = df_cities[['city_clean', 'state_clean', 'LATITUDE', 'LONGITUDE']].drop_duplicates(
                subset=['city_clean', 'state_clean']
            )

            merged = pd.merge(df_fuel, cities_coords, on=['city_clean', 'state_clean'], how='left')
            merged.rename(columns={'LATITUDE': 'latitude', 'LONGITUDE': 'longitude'}, inplace=True)
            merged.drop(columns=['city_clean', 'state_clean'], inplace=True, errors='ignore')
            merged.to_csv(output_csv_path, index=False)
            return merged
        except Exception as e:
            logger.error(f"Failed to fetch US cities database: {e}")
            df_fuel['latitude'] = np.nan
            df_fuel['longitude'] = np.nan
            return df_fuel

    def find_nearby_stations(self, route_points, max_distance_miles=10.0):
        """
        Given a list of (lat, lon) coordinates along the driving route,
        returns all unique fuel stations within max_distance_miles of the route.
        """
        if self._tree is None or len(route_points) == 0:
            return pd.DataFrame()

        # Convert query distance in miles to chord distance in 3D unit sphere
        # chord_length = 2 * sin(distance / (2 * R))
        radius_rad = max_distance_miles / EARTH_RADIUS_MILES
        chord_threshold = 2.0 * math.sin(radius_rad / 2.0)

        query_cartesian = lat_lon_to_cartesian(
            [p[0] for p in route_points],
            [p[1] for p in route_points]
        )

        # Query KDTree for all stations within threshold of any route point
        station_indices = set()
        matched = self._tree.query_ball_point(query_cartesian, r=chord_threshold)
        for sublist in matched:
            station_indices.update(sublist)

        if not station_indices:
            return pd.DataFrame()

        nearby_df = self._df.iloc[list(station_indices)].copy()
        return nearby_df
