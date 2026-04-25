from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from unittest.mock import patch, MagicMock
from .services import FuelDataService, FuelStopOptimizer


class HealthCheckTests(APITestCase):
    def test_health_check_returns_200(self):
        url = reverse('health-check')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_health_check_status_healthy(self):
        url = reverse('health-check')
        response = self.client.get(url)
        self.assertEqual(response.data['status'], 'healthy')

    def test_health_check_fuel_database_loaded(self):
        url = reverse('health-check')
        response = self.client.get(url)
        self.assertTrue(response.data['fuel_database']['loaded'])

    def test_health_check_vehicle_settings(self):
        url = reverse('health-check')
        response = self.client.get(url)
        vehicle = response.data['vehicle_settings']
        self.assertEqual(vehicle['max_range_miles'], 500)
        self.assertEqual(vehicle['fuel_efficiency_mpg'], 10)
        self.assertEqual(vehicle['tank_capacity_gallons'], 50.0)


class FuelStatsTests(APITestCase):
    def test_fuel_stats_returns_200(self):
        url = reverse('fuel-stats')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_fuel_stats_has_required_fields(self):
        url = reverse('fuel-stats')
        response = self.client.get(url)
        data = response.data['data']
        self.assertIn('total_stations', data)
        self.assertIn('cheapest_price', data)
        self.assertIn('most_expensive_price', data)
        self.assertIn('average_price', data)

    def test_fuel_stats_prices_are_valid(self):
        url = reverse('fuel-stats')
        response = self.client.get(url)
        data = response.data['data']
        self.assertGreater(data['total_stations'], 0)
        self.assertGreater(data['cheapest_price'], 0)
        self.assertLess(data['cheapest_price'], data['most_expensive_price'])


class CheapestFuelByStateTests(APITestCase):
    def test_valid_state_returns_200(self):
        url = reverse('fuel-by-state') + '?state=TX'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_missing_state_returns_400(self):
        url = reverse('fuel-by-state')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_state_returns_404(self):
        url = reverse('fuel-by-state') + '?state=ZZ'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_lowercase_state_works(self):
        url = reverse('fuel-by-state') + '?state=tx'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_response_has_stations(self):
        url = reverse('fuel-by-state') + '?state=TX'
        response = self.client.get(url)
        self.assertIn('cheapest_stations', response.data)
        self.assertGreater(len(response.data['cheapest_stations']), 0)


class RoutePlannerTests(APITestCase):
    def test_missing_params_returns_400(self):
        url = reverse('route-planner')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_finish_returns_400(self):
        url = reverse('route-planner') + '?start=New York, NY'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_same_start_finish_returns_400(self):
        url = reverse('route-planner') + '?start=New York, NY&finish=New York, NY'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch('route_planner.views.GeocodingService.geocode')
    @patch('route_planner.views.RouteService.get_route')
    def test_valid_route_returns_200(self, mock_route, mock_geocode):
        mock_geocode.side_effect = [
            {'lat': 40.68, 'lon': -73.97, 'display_name': 'New York, NY, USA'},
            {'lat': 41.87, 'lon': -87.66, 'display_name': 'Chicago, IL, USA'},
        ]
        mock_route.return_value = {
            'features': [{
                'geometry': {
                    'type': 'LineString',
                    'coordinates': [[-73.97, 40.68], [-87.66, 41.87]]
                },
                'properties': {
                    'summary': {'distance': 790.0, 'duration': 49000}
                }
            }]
        }
        url = reverse('route-planner') + '?start=New York, NY&finish=Chicago, IL'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])

    @patch('route_planner.views.GeocodingService.geocode')
    @patch('route_planner.views.RouteService.get_route')
    def test_response_has_all_required_fields(self, mock_route, mock_geocode):
        mock_geocode.side_effect = [
            {'lat': 40.68, 'lon': -73.97, 'display_name': 'New York, NY, USA'},
            {'lat': 41.87, 'lon': -87.66, 'display_name': 'Chicago, IL, USA'},
        ]
        mock_route.return_value = {
            'features': [{
                'geometry': {
                    'type': 'LineString',
                    'coordinates': [[-73.97, 40.68], [-87.66, 41.87]]
                },
                'properties': {
                    'summary': {'distance': 790.0, 'duration': 49000}
                }
            }]
        }
        url = reverse('route-planner') + '?start=New York, NY&finish=Chicago, IL'
        response = self.client.get(url)
        self.assertIn('trip', response.data)
        self.assertIn('vehicle', response.data)
        self.assertIn('fuel_optimization', response.data)
        self.assertIn('map', response.data)
        self.assertIn('summary', response.data)


class FuelStopOptimizerTests(TestCase):
    def test_haversine_distance_same_point(self):
        dist = FuelStopOptimizer.haversine_distance(40.0, -74.0, 40.0, -74.0)
        self.assertEqual(dist, 0.0)

    def test_haversine_distance_known_cities(self):
        # NY to LA approx 2445 miles
        dist = FuelStopOptimizer.haversine_distance(
            40.71, -74.01, 34.05, -118.24
        )
        self.assertGreater(dist, 2000)
        self.assertLess(dist, 3000)

    def test_state_coords_returns_tuple(self):
        coords = FuelStopOptimizer._lookup_state_center('TX')
        self.assertIsInstance(coords, tuple)
        self.assertEqual(len(coords), 2)

    def test_unknown_state_returns_default(self):
        coords = FuelStopOptimizer._lookup_state_center('ZZ')
        self.assertEqual(coords, (39.5, -98.35))


class FuelDataServiceTests(TestCase):
    def test_singleton_pattern(self):
        instance1 = FuelDataService.get_instance()
        instance2 = FuelDataService.get_instance()
        self.assertIs(instance1, instance2)

    def test_fuel_data_loaded(self):
        service = FuelDataService.get_instance()
        df = service.get_fuel_data()
        self.assertGreater(len(df), 0)

    def test_get_stats_returns_dict(self):
        service = FuelDataService.get_instance()
        stats = service.get_stats()
        self.assertIsInstance(stats, dict)

    def test_cheapest_in_valid_state(self):
        service = FuelDataService.get_instance()
        stations = service.get_cheapest_in_state('TX')
        self.assertIsNotNone(stations)
        self.assertGreater(len(stations), 0)

    def test_cheapest_in_invalid_state(self):
        service = FuelDataService.get_instance()
        stations = service.get_cheapest_in_state('ZZ')
        self.assertIsNone(stations)