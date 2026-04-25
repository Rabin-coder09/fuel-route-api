import pandas as pd
import requests
import math
import os
from django.conf import settings
from django.core.cache import cache
import hashlib
import json

class FuelDataService:
    _instance = None
    _fuel_data = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self._load_fuel_data()

    def _load_fuel_data(self):
        try:
            df = pd.read_csv(settings.FUEL_DATA_PATH)
            df.columns = df.columns.str.strip()
            df['City'] = df['City'].str.strip()
            df['State'] = df['State'].str.strip()
            df['Retail Price'] = pd.to_numeric(df['Retail Price'], errors='coerce')
            df = df.dropna(subset=['Retail Price'])
            # Keep cheapest price per city+state
            self._fuel_data = df.sort_values('Retail Price').drop_duplicates(
                subset=['City', 'State'], keep='first'
            ).reset_index(drop=True)
        except Exception as e:
            raise Exception(f"Failed to load fuel data: {str(e)}")

    def get_fuel_data(self):
        return self._fuel_data

    def get_cheapest_in_state(self, state):
        df = self._fuel_data
        state_data = df[df['State'] == state]
        if state_data.empty:
            return None
        return state_data.nsmallest(3, 'Retail Price').to_dict('records')

    def get_stats(self):
        df = self._fuel_data
        return {
            'total_stations': len(df),
            'total_states': df['State'].nunique(),
            'cheapest_price': round(float(df['Retail Price'].min()), 3),
            'most_expensive_price': round(float(df['Retail Price'].max()), 3),
            'average_price': round(float(df['Retail Price'].mean()), 3),
            'cheapest_station': df.loc[df['Retail Price'].idxmin(), 'Truckstop Name'],
            'cheapest_city': df.loc[df['Retail Price'].idxmin(), 'City'],
            'cheapest_state': df.loc[df['Retail Price'].idxmin(), 'State'],
        }


class GeocodingService:
    ORS_BASE = settings.ORS_BASE_URL
    API_KEY = settings.ORS_API_KEY

    @classmethod
    def geocode(cls, location: str) -> dict:
        cache_key = f"geocode_{hashlib.md5(location.encode()).hexdigest()}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        url = f"{cls.ORS_BASE}/geocode/search"
        params = {
            'api_key': cls.API_KEY,
            'text': f"{location}, USA",
            'boundary.country': 'US',
            'size': 1,
        }
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if not data.get('features'):
            raise ValueError(f"Location not found: {location}")

        feature = data['features'][0]
        coords = feature['geometry']['coordinates']
        props = feature['properties']

        result = {
            'lon': coords[0],
            'lat': coords[1],
            'display_name': props.get('label', location),
            'state': props.get('region', ''),
            'city': props.get('locality', location),
        }
        cache.set(cache_key, result, 3600)
        return result


class RouteService:
    ORS_BASE = settings.ORS_BASE_URL
    API_KEY = settings.ORS_API_KEY
    MAX_RANGE = settings.VEHICLE_MAX_RANGE_MILES
    MPG = settings.VEHICLE_MPG
    KM_TO_MILES = 0.621371

    @classmethod
    def get_route(cls, start_coords: list, end_coords: list) -> dict:
        """Get route from ORS - ONE API call only"""
        cache_key = f"route_{start_coords[0]}_{start_coords[1]}_{end_coords[0]}_{end_coords[1]}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        url = f"{cls.ORS_BASE}/v2/directions/driving-car/geojson"
        headers = {
            'Authorization': cls.API_KEY,
            'Content-Type': 'application/json',
        }
        body = {
            "coordinates": [start_coords, end_coords],
            "instructions": True,
            "language": "en",
            "units": "mi",
            "geometry": True,
            "extra_info": ["waytype", "steepness"],
        }

        response = requests.post(url, json=body, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        cache.set(cache_key, data, 3600)
        return data

    @classmethod
    def extract_route_points(cls, route_data: dict) -> list:
        """Extract coordinate points along the route"""
        coordinates = route_data['features'][0]['geometry']['coordinates']
        # Sample every Nth point to get manageable waypoints
        step = max(1, len(coordinates) // 50)
        sampled = coordinates[::step]
        if coordinates[-1] not in sampled:
            sampled.append(coordinates[-1])
        return sampled

    @classmethod
    def get_route_distance_miles(cls, route_data: dict) -> float:
        summary = route_data['features'][0]['properties']['summary']
        return summary['distance']

    @classmethod  
    def get_route_duration_seconds(cls, route_data: dict) -> float:
        summary = route_data['features'][0]['properties']['summary']
        return summary['duration']


class FuelStopOptimizer:
    MAX_RANGE = settings.VEHICLE_MAX_RANGE_MILES
    MPG = settings.VEHICLE_MPG
    TANK_CAPACITY = MAX_RANGE / MPG  # 50 gallons

    @classmethod
    def haversine_distance(cls, lat1, lon1, lat2, lon2) -> float:
        """Calculate distance between two coordinates in miles"""
        R = 3959  # Earth radius in miles
        lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        return R * c

    @classmethod
    def find_nearest_stations(cls, lat, lon, fuel_df, radius_miles=100, top_n=5):
        """Find nearest fuel stations within radius"""
        stations = []
        for _, row in fuel_df.iterrows():
            city = row['City']
            state = row['State']
            # Get approximate coords for city
            city_coords = cls._get_city_coords(city, state)
            if city_coords:
                dist = cls.haversine_distance(lat, lon, city_coords[0], city_coords[1])
                if dist <= radius_miles:
                    stations.append({
                        'name': row['Truckstop Name'],
                        'city': city,
                        'state': state,
                        'address': row['Address'],
                        'price': float(row['Retail Price']),
                        'distance_from_point': round(dist, 2),
                        'lat': city_coords[0],
                        'lon': city_coords[1],
                    })
        # Sort by price (cheapest first), then distance
        stations.sort(key=lambda x: (x['price'], x['distance_from_point']))
        return stations[:top_n]

    @classmethod
    def _get_city_coords(cls, city, state) -> tuple:
        """Get approximate coordinates for a city using cache"""
        cache_key = f"city_coords_{city}_{state}".replace(' ', '_')
        cached = cache.get(cache_key)
        if cached:
            return cached

        # Use built-in city coordinates for major cities
        # This avoids extra API calls
        coords = cls._lookup_state_center(state)
        cache.set(cache_key, coords, 86400)
        return coords

    @classmethod
    def _lookup_state_center(cls, state) -> tuple:
        """Approximate center coordinates for US states"""
        state_coords = {
            'AL': (32.806671, -86.791130), 'AK': (61.370716, -152.404419),
            'AZ': (33.729759, -111.431221), 'AR': (34.969704, -92.373123),
            'CA': (36.116203, -119.681564), 'CO': (39.059811, -105.311104),
            'CT': (41.597782, -72.755371), 'DE': (39.318523, -75.507141),
            'FL': (27.766279, -81.686783), 'GA': (33.040619, -83.643074),
            'HI': (21.094318, -157.498337), 'ID': (44.240459, -114.478828),
            'IL': (40.349457, -88.986137), 'IN': (39.849426, -86.258278),
            'IA': (42.011539, -93.210526), 'KS': (38.526600, -96.726486),
            'KY': (37.668140, -84.670067), 'LA': (31.169960, -91.867805),
            'ME': (44.693947, -69.381927), 'MD': (39.063946, -76.802101),
            'MA': (42.230171, -71.530106), 'MI': (43.326618, -84.536095),
            'MN': (45.694454, -93.900192), 'MS': (32.741646, -89.678696),
            'MO': (38.456085, -92.288368), 'MT': (46.921925, -110.454353),
            'NE': (41.125370, -98.268082), 'NV': (38.313515, -117.055374),
            'NH': (43.452492, -71.563896), 'NJ': (40.298904, -74.521011),
            'NM': (34.840515, -106.248482), 'NY': (42.165726, -74.948051),
            'NC': (35.630066, -79.806419), 'ND': (47.528912, -99.784012),
            'OH': (40.388783, -82.764915), 'OK': (35.565342, -96.928917),
            'OR': (44.572021, -122.070938), 'PA': (40.590752, -77.209755),
            'RI': (41.680893, -71.511780), 'SC': (33.856892, -80.945007),
            'SD': (44.299782, -99.438828), 'TN': (35.747845, -86.692345),
            'TX': (31.054487, -97.563461), 'UT': (40.150032, -111.862434),
            'VT': (44.045876, -72.710686), 'VA': (37.769337, -78.169968),
            'WA': (47.400902, -121.490494), 'WV': (38.491226, -80.954453),
            'WI': (44.268543, -89.616508), 'WY': (42.755966, -107.302490),
        }
        return state_coords.get(state, (39.5, -98.35))  # Default to US center

    @classmethod
    def optimize_fuel_stops(cls, route_points: list, total_distance: float, 
                             fuel_df, start_location: dict, end_location: dict) -> dict:
        """
        Main optimization algorithm:
        - Plan fuel stops every ~400 miles (buffer before 500 limit)
        - At each stop window, find cheapest station
        """
        fuel_stops = []
        current_fuel_miles = cls.MAX_RANGE  # Start with full tank
        miles_since_last_stop = 0
        total_fuel_cost = 0.0
        total_gallons = 0.0
        
        REFUEL_THRESHOLD = 400  # Refuel before hitting 500 mile limit
        SEARCH_RADIUS = 150  # Miles radius to search for stations

        # Sample route points at intervals
        num_points = len(route_points)
        miles_per_point = total_distance / max(num_points - 1, 1)

        for i, point in enumerate(route_points):
            current_miles = i * miles_per_point
            miles_since_last_stop = current_miles - (
                fuel_stops[-1]['miles_into_trip'] if fuel_stops else 0
            )
            remaining_distance = total_distance - current_miles

            # Check if we need to refuel
            needs_refuel = (
                miles_since_last_stop >= REFUEL_THRESHOLD and 
                remaining_distance > 50  # Don't stop if almost there
            )

            if needs_refuel:
                lon, lat = point[0], point[1]
                nearby_stations = cls.find_nearest_stations(
                    lat, lon, fuel_df, radius_miles=SEARCH_RADIUS
                )

                if nearby_stations:
                    best_station = nearby_stations[0]
                    
                    # Calculate fuel needed
                    miles_to_fill = min(miles_since_last_stop, cls.MAX_RANGE)
                    gallons_needed = miles_to_fill / cls.MPG
                    cost = gallons_needed * best_station['price']
                    
                    total_fuel_cost += cost
                    total_gallons += gallons_needed

                    fuel_stops.append({
                        'stop_number': len(fuel_stops) + 1,
                        'station_name': best_station['name'],
                        'city': best_station['city'],
                        'state': best_station['state'],
                        'address': best_station['address'],
                        'price_per_gallon': best_station['price'],
                        'gallons_purchased': round(gallons_needed, 2),
                        'cost_at_stop': round(cost, 2),
                        'miles_into_trip': round(current_miles, 1),
                        'miles_remaining': round(remaining_distance, 1),
                        'lat': best_station['lat'],
                        'lon': best_station['lon'],
                        'nearby_alternatives': nearby_stations[1:3],  # Show 2 alternatives
                    })

        # Calculate final leg fuel cost
        last_stop_miles = fuel_stops[-1]['miles_into_trip'] if fuel_stops else 0
        final_leg_miles = total_distance - last_stop_miles
        final_gallons = final_leg_miles / cls.MPG
        final_cost = final_gallons * cls._get_average_price(fuel_df)
        total_fuel_cost += final_cost
        total_gallons += final_gallons

        return {
            'fuel_stops': fuel_stops,
            'total_fuel_cost': round(total_fuel_cost, 2),
            'total_gallons': round(total_gallons, 2),
            'average_price_paid': round(total_fuel_cost / total_gallons if total_gallons > 0 else 0, 3),
            'number_of_stops': len(fuel_stops),
            'savings_vs_average': cls._calculate_savings(fuel_stops, total_gallons, fuel_df),
        }

    @classmethod
    def _get_average_price(cls, fuel_df) -> float:
        return float(fuel_df['Retail Price'].mean())

    @classmethod
    def _calculate_savings(cls, fuel_stops, total_gallons, fuel_df) -> float:
        avg_price = cls._get_average_price(fuel_df)
        cost_at_avg = total_gallons * avg_price
        actual_cost = sum(s['cost_at_stop'] for s in fuel_stops)
        return round(cost_at_avg - actual_cost, 2)