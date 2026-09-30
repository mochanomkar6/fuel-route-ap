import math
import numpy as np
import pandas as pd
from routing.fuel_service import FuelService, EARTH_RADIUS_MILES

TANK_CAPACITY_MILES = 500.0  # Maximum range on full tank
MILES_PER_GALLON = 10.0      # 10 MPG


def haversine_distance(lat1, lon1, lat2, lon2):
    """Calculates great-circle distance between two GPS coordinates in miles."""
    lat1_rad, lon1_rad = math.radians(lat1), math.radians(lon1)
    lat2_rad, lon2_rad = math.radians(lat2), math.radians(lon2)

    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad

    a = math.sin(dlat / 2.0)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2.0)**2
    c = 2.0 * math.asin(math.sqrt(a))
    return EARTH_RADIUS_MILES * c


class RouteOptimizer:
    def __init__(self, route_data):
        self.route_data = route_data
        self.coordinates = route_data["coordinates"]  # [[lon, lat], ...]
        self.total_distance = route_data["total_distance_miles"]
        self.fuel_service = FuelService.get_instance()

    def _build_route_mile_markers(self):
        """
        Computes cumulative distance in miles for each coordinate point along the route.
        """
        cum_dist = [0.0]
        for i in range(1, len(self.coordinates)):
            prev_lon, prev_lat = self.coordinates[i - 1]
            curr_lon, curr_lat = self.coordinates[i]
            d = haversine_distance(prev_lat, prev_lon, curr_lat, curr_lon)
            cum_dist.append(cum_dist[-1] + d)
        return cum_dist

    def _map_stations_to_route(self, nearby_df, cum_dist):
        """
        For each nearby station, determines its mile marker (distance from start)
        along the highway.
        """
        if nearby_df.empty:
            return []

        route_lons = np.array([p[0] for p in self.coordinates])
        route_lats = np.array([p[1] for p in self.coordinates])
        cum_dist_arr = np.array(cum_dist)

        stations = []
        for _, row in nearby_df.iterrows():
            st_lat, st_lon = row["latitude"], row["longitude"]

            # Fast Euclidean approximation for closest route point index
            # Scale lon by cos(lat) for projection accuracy
            dlat = route_lats - st_lat
            dlon = (route_lons - st_lon) * np.cos(np.radians(st_lat))
            dists_sq = dlat**2 + dlon**2
            closest_idx = int(np.argmin(dists_sq))

            mile_marker = float(cum_dist_arr[closest_idx])

            # Only include stations between start and destination
            if 0 <= mile_marker <= self.total_distance:
                stations.append({
                    "id": row.get("OPIS Truckstop ID", ""),
                    "name": row.get("Truckstop Name", "").strip(),
                    "address": row.get("Address", "").strip(),
                    "city": row.get("City", "").strip(),
                    "state": row.get("State", "").strip(),
                    "price": float(row["Retail Price"]),
                    "lat": float(st_lat),
                    "lon": float(st_lon),
                    "mile_marker": round(mile_marker, 2)
                })

        # Sort stations in order of route progression
        stations.sort(key=lambda s: s["mile_marker"])
        return stations

    def optimize_fuel_stops(self):
        """
        Computes optimal fuel stops along the route.
        Enforces 500-mile max range and selects the cheapest fuel stop within reach.
        """
        # Step 1: Calculate cumulative mile markers along route polyline
        cum_dist = self._build_route_mile_markers()

        # Step 2: Find all stations within 10 miles of highway
        # Query every 10th route point for speed
        sampled_points = [(p[1], p[0]) for p in self.coordinates[::10]]
        nearby_df = self.fuel_service.find_nearby_stations(sampled_points, max_distance_miles=10.0)

        # Step 3: Map stations to route mile markers
        stations = self._map_stations_to_route(nearby_df, cum_dist)

        # Step 4: Greedy Fuel Stop Selection
        selected_stops = []
        current_mile = 0.0
        current_fuel_range = TANK_CAPACITY_MILES  # Start with full tank (500 miles)
        total_money_spent = 0.0
        while (self.total_distance - current_mile) > current_fuel_range:
            max_reachable_mile = current_mile + current_fuel_range

            # Ideal refueling window: when tank is in its last 200 miles (between 300 and 485 miles driven)
            window_start = current_mile + 300.0
            window_end = max_reachable_mile - 15.0

            candidates = [
                s for s in stations
                if window_start <= s["mile_marker"] <= window_end
            ]

            # If no station in the ideal window, expand search to any station ahead
            if not candidates:
                candidates = [
                    s for s in stations
                    if current_mile + 20.0 <= s["mile_marker"] <= max_reachable_mile - 10.0
                ]

            if not candidates:
                # Farthest reachable station ahead before running out of fuel
                fallback = [s for s in stations if current_mile < s["mile_marker"] <= max_reachable_mile]
                if fallback:
                    chosen = fallback[-1]
                else:
                    break
            else:
                # Pick the cheapest station in the reachable window
                chosen = min(candidates, key=lambda s: s["price"])

            distance_driven = chosen["mile_marker"] - current_mile
            gallons_burned = distance_driven / MILES_PER_GALLON
            gallons_to_fill = gallons_burned
            cost = round(gallons_to_fill * chosen["price"], 2)

            selected_stops.append({
                "truckstop_id": chosen["id"],
                "name": chosen["name"],
                "address": chosen["address"],
                "city": chosen["city"],
                "state": chosen["state"],
                "latitude": chosen["lat"],
                "longitude": chosen["lon"],
                "price_per_gallon": chosen["price"],
                "mile_marker": chosen["mile_marker"],
                "gallons_purchased": round(gallons_to_fill, 2),
                "cost": cost
            })

            total_money_spent += cost
            current_mile = chosen["mile_marker"]
            current_fuel_range = TANK_CAPACITY_MILES  # Tank is full again

        # If any fuel stops were made, calculate final leg fuel to return accurate total cost
        total_gallons_consumed = round(self.total_distance / MILES_PER_GALLON, 2)

        return {
            "total_distance_miles": self.total_distance,
            "total_gallons_consumed": total_gallons_consumed,
            "total_fuel_cost": round(total_money_spent, 2),
            "number_of_stops": len(selected_stops),
            "fuel_stops": selected_stops
        }
