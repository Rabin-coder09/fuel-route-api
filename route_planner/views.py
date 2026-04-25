import requests
import time
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from drf_spectacular.types import OpenApiTypes
from django.conf import settings

from .services import (
    FuelDataService,
    GeocodingService,
    RouteService,
    FuelStopOptimizer,
)


class HealthCheckView(APIView):
    """Health check endpoint"""

    @extend_schema(
        summary="Health Check",
        description="Check if the API is running properly",
        tags=["System"],
    )
    def get(self, request):
        fuel_service = FuelDataService.get_instance()
        stats = fuel_service.get_stats()
        return Response({
            "status": "healthy",
            "message": "Fuel Route Optimizer API is running",
            "fuel_database": {
                "loaded": True,
                "total_stations": stats['total_stations'],
                "states_covered": stats['total_states'],
            },
            "vehicle_settings": {
                "max_range_miles": settings.VEHICLE_MAX_RANGE_MILES,
                "fuel_efficiency_mpg": settings.VEHICLE_MPG,
                "tank_capacity_gallons": settings.VEHICLE_MAX_RANGE_MILES / settings.VEHICLE_MPG,
            },
            "api_version": "1.0.0",
        })


class FuelStatsView(APIView):
    """Fuel price statistics"""

    @extend_schema(
        summary="Fuel Price Statistics",
        description="Get statistics about fuel prices across the USA",
        tags=["Fuel Data"],
    )
    def get(self, request):
        fuel_service = FuelDataService.get_instance()
        stats = fuel_service.get_stats()
        return Response({
            "success": True,
            "data": stats,
        })


class CheapestFuelByStateView(APIView):
    """Get cheapest fuel by state"""

    @extend_schema(
        summary="Cheapest Fuel By State",
        description="Get the cheapest fuel stations in a specific state",
        parameters=[
            OpenApiParameter(
                name='state',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description='Two-letter state code (e.g., TX, CA, NY)',
                required=True,
            )
        ],
        tags=["Fuel Data"],
    )
    def get(self, request):
        state = request.query_params.get('state', '').upper().strip()
        if not state:
            return Response(
                {"success": False, "error": "State parameter is required (e.g., ?state=TX)"},
                status=status.HTTP_400_BAD_REQUEST
            )

        fuel_service = FuelDataService.get_instance()
        stations = fuel_service.get_cheapest_in_state(state)

        if not stations:
            return Response(
                {"success": False, "error": f"No fuel data found for state: {state}"},
                status=status.HTTP_404_NOT_FOUND
            )

        return Response({
            "success": True,
            "state": state,
            "cheapest_stations": stations,
        })


class RoutePlannerView(APIView):
    """Main route planning endpoint"""

    @extend_schema(
        summary="Plan Optimal Fuel Route",
        description="""
        ## Plan your optimal fuel route across the USA

        This endpoint:
        - Calculates the best route from start to finish
        - Finds the most cost-effective fuel stops (max 500 mile range)
        - Returns total fuel cost at 10 MPG
        - Shows alternative fuel stations at each stop
        - Returns map data for visualization

        ### Tips:
        - Use city names like "New York, NY" or "Los Angeles, CA"
        - The algorithm finds cheapest fuel within 150 miles of your route
        """,
        parameters=[
            OpenApiParameter(
                name='start',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description='Start location (e.g., "New York, NY")',
                required=True,
                examples=[
                    OpenApiExample('New York', value='New York, NY'),
                    OpenApiExample('Los Angeles', value='Los Angeles, CA'),
                ]
            ),
            OpenApiParameter(
                name='finish',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description='Finish location (e.g., "Los Angeles, CA")',
                required=True,
                examples=[
                    OpenApiExample('Chicago', value='Chicago, IL'),
                    OpenApiExample('Miami', value='Miami, FL'),
                ]
            ),
        ],
        tags=["Route Planner"],
    )
    def get(self, request):
        start_time = time.time()

        # Get parameters
        start = request.query_params.get('start', '').strip()
        finish = request.query_params.get('finish', '').strip()

        # Validate inputs
        if not start or not finish:
            return Response(
                {
                    "success": False,
                    "error": "Both 'start' and 'finish' parameters are required",
                    "example": "/api/route/?start=New York, NY&finish=Los Angeles, CA"
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        if start.lower() == finish.lower():
            return Response(
                {"success": False, "error": "Start and finish locations must be different"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Step 1: Geocode both locations
            start_geo = GeocodingService.geocode(start)
            finish_geo = GeocodingService.geocode(finish)

            # Step 2: Get route (ONE API call)
            route_data = RouteService.get_route(
                [start_geo['lon'], start_geo['lat']],
                [finish_geo['lon'], finish_geo['lat']]
            )

            # Step 3: Extract route info
            total_distance = RouteService.get_route_distance_miles(route_data)
            total_duration = RouteService.get_route_duration_seconds(route_data)
            route_points = RouteService.extract_route_points(route_data)

            # Step 4: Load fuel data
            fuel_service = FuelDataService.get_instance()
            fuel_df = fuel_service.get_fuel_data()

            # Step 5: Optimize fuel stops
            optimization = FuelStopOptimizer.optimize_fuel_stops(
                route_points,
                total_distance,
                fuel_df,
                start_geo,
                finish_geo,
            )

            # Step 6: Build response
            elapsed = round(time.time() - start_time, 2)

            response_data = {
                "success": True,
                "processing_time_seconds": elapsed,
                "trip": {
                    "start": {
                        "input": start,
                        "display_name": start_geo['display_name'],
                        "coordinates": {
                            "lat": start_geo['lat'],
                            "lon": start_geo['lon'],
                        }
                    },
                    "finish": {
                        "input": finish,
                        "display_name": finish_geo['display_name'],
                        "coordinates": {
                            "lat": finish_geo['lat'],
                            "lon": finish_geo['lon'],
                        }
                    },
                    "distance_miles": round(total_distance, 1),
                    "estimated_duration": RoutePlannerView._format_duration(total_duration),
                    "estimated_duration_seconds": int(total_duration),
                },
                "vehicle": {
                    "max_range_miles": settings.VEHICLE_MAX_RANGE_MILES,
                    "fuel_efficiency_mpg": settings.VEHICLE_MPG,
                    "tank_capacity_gallons": settings.VEHICLE_MAX_RANGE_MILES / settings.VEHICLE_MPG,
                },
                "fuel_optimization": {
                    "number_of_stops": optimization['number_of_stops'],
                    "total_fuel_cost_usd": optimization['total_fuel_cost'],
                    "total_gallons_needed": optimization['total_gallons'],
                    "average_price_per_gallon": optimization['average_price_paid'],
                    "estimated_savings_vs_avg_usd": optimization['savings_vs_average'],
                    "fuel_stops": optimization['fuel_stops'],
                },
                "map": {
                    "route_geometry": route_data['features'][0]['geometry'],
                    "start_marker": {
                        "lat": start_geo['lat'],
                        "lon": start_geo['lon'],
                        "label": start_geo['display_name'],
                        "type": "start",
                    },
                    "end_marker": {
                        "lat": finish_geo['lat'],
                        "lon": finish_geo['lon'],
                        "label": finish_geo['display_name'],
                        "type": "end",
                    },
                    "fuel_stop_markers": [
                        {
                            "lat": stop['lat'],
                            "lon": stop['lon'],
                            "label": f"Stop {stop['stop_number']}: {stop['station_name']}",
                            "price": stop['price_per_gallon'],
                            "type": "fuel_stop",
                        }
                        for stop in optimization['fuel_stops']
                    ],
                },
                "summary": RoutePlannerView._build_summary(
                    total_distance,
                    total_duration,
                    optimization,
                ),
            }

            return Response(response_data, status=status.HTTP_200_OK)

        except ValueError as e:
            return Response(
                {"success": False, "error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except requests.exceptions.RequestException as e:
            return Response(
                {"success": False, "error": f"Routing service error: {str(e)}"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        except Exception as e:
            return Response(
                {"success": False, "error": f"Internal error: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @staticmethod
    def _format_duration(seconds: float) -> str:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        if hours > 0:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"

    @staticmethod
    def _build_summary(distance, duration, optimization) -> dict:
        hours = int(duration // 3600)
        minutes = int((duration % 3600) // 60)
        return {
            "total_distance": f"{round(distance, 1)} miles",
            "driving_time": f"{hours}h {minutes}m",
            "fuel_stops": optimization['number_of_stops'],
            "total_fuel_cost": f"${optimization['total_fuel_cost']}",
            "total_gallons": f"{optimization['total_gallons']} gallons",
            "you_save": f"${optimization['savings_vs_average']} vs average prices",
        }