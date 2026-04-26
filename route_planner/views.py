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
    @extend_schema(summary="Health Check", tags=["System"])
    def get(self, request):
        fuel_service = FuelDataService.get_instance()
        stats = fuel_service.get_stats()
        return Response({
            "status": "healthy",
            "message": "Fuel Route Optimizer API is running",
            "fuel_database": {"loaded": True, "total_stations": stats['total_stations'], "states_covered": stats['total_states']},
            "vehicle_settings": {"max_range_miles": settings.VEHICLE_MAX_RANGE_MILES, "fuel_efficiency_mpg": settings.VEHICLE_MPG, "tank_capacity_gallons": settings.VEHICLE_MAX_RANGE_MILES / settings.VEHICLE_MPG},
            "api_version": "1.0.0",
        })


class FuelStatsView(APIView):
    @extend_schema(summary="Fuel Price Statistics", tags=["Fuel Data"])
    def get(self, request):
        fuel_service = FuelDataService.get_instance()
        stats = fuel_service.get_stats()
        return Response({"success": True, "data": stats})


class CheapestFuelByStateView(APIView):
    @extend_schema(
        summary="Cheapest Fuel By State", tags=["Fuel Data"],
        parameters=[OpenApiParameter(name='state', type=OpenApiTypes.STR, location=OpenApiParameter.QUERY, required=True)]
    )
    def get(self, request):
        state = request.query_params.get('state', '').upper().strip()
        if not state:
            return Response({"success": False, "error": "State parameter is required"}, status=status.HTTP_400_BAD_REQUEST)
        fuel_service = FuelDataService.get_instance()
        stations = fuel_service.get_cheapest_in_state(state)
        if not stations:
            return Response({"success": False, "error": f"No fuel data for state: {state}"}, status=status.HTTP_404_NOT_FOUND)
        return Response({"success": True, "state": state, "cheapest_stations": stations})


class FuelPriceRankingView(APIView):
    @extend_schema(
        summary="Fuel Price Ranking by State",
        description="Returns all states ranked by average fuel price, cheapest first. Used for heatmap and ranking table.",
        tags=["Fuel Data"]
    )
    def get(self, request):
        fuel_service = FuelDataService.get_instance()
        df = fuel_service.get_fuel_data()

        # Group by state and calculate stats
        state_stats = df.groupby('State')['Retail Price'].agg(['mean', 'min', 'max', 'count']).reset_index()
        state_stats.columns = ['state', 'avg_price', 'min_price', 'max_price', 'station_count']
        state_stats = state_stats.sort_values('avg_price')
        state_stats['avg_price'] = state_stats['avg_price'].round(3)
        state_stats['min_price'] = state_stats['min_price'].round(3)
        state_stats['max_price'] = state_stats['max_price'].round(3)
        state_stats['rank'] = range(1, len(state_stats) + 1)

        overall_avg = round(float(df['Retail Price'].mean()), 3)

        rankings = state_stats.to_dict('records')

        return Response({
            "success": True,
            "overall_average_price": overall_avg,
            "total_states": len(rankings),
            "rankings": rankings,
        })


class RoutePlannerView(APIView):
    @extend_schema(
        summary="Plan Optimal Fuel Route",
        description="Calculates optimal fuel stops for a road trip. Returns route geometry, fuel stops, costs, and map data.",
        parameters=[
            OpenApiParameter(name='start', type=OpenApiTypes.STR, location=OpenApiParameter.QUERY, required=True,
                examples=[OpenApiExample('New York', value='New York, NY')]),
            OpenApiParameter(name='finish', type=OpenApiTypes.STR, location=OpenApiParameter.QUERY, required=True,
                examples=[OpenApiExample('Los Angeles', value='Los Angeles, CA')]),
        ],
        tags=["Route Planner"],
    )
    def get(self, request):
        start_time = time.time()
        start = request.query_params.get('start', '').strip()
        finish = request.query_params.get('finish', '').strip()

        if not start or not finish:
            return Response({"success": False, "error": "Both 'start' and 'finish' parameters are required",
                "example": "/api/route/?start=New York, NY&finish=Los Angeles, CA"},
                status=status.HTTP_400_BAD_REQUEST)

        if start.lower() == finish.lower():
            return Response({"success": False, "error": "Start and finish must be different"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            start_geo = GeocodingService.geocode(start)
            finish_geo = GeocodingService.geocode(finish)
            route_data = RouteService.get_route([start_geo['lon'], start_geo['lat']], [finish_geo['lon'], finish_geo['lat']])
            total_distance = RouteService.get_route_distance_miles(route_data)
            total_duration = RouteService.get_route_duration_seconds(route_data)
            route_points = RouteService.extract_route_points(route_data)
            fuel_service = FuelDataService.get_instance()
            fuel_df = fuel_service.get_fuel_data()
            optimization = FuelStopOptimizer.optimize_fuel_stops(route_points, total_distance, fuel_df, start_geo, finish_geo)
            elapsed = round(time.time() - start_time, 2)

            # Build cost chart data
            chart_data = []
            cumulative = 0
            for stop in optimization['fuel_stops']:
                cumulative += stop['cost_at_stop']
                chart_data.append({
                    'stop': f"Stop {stop['stop_number']}",
                    'station': stop['station_name'],
                    'city': stop['city'],
                    'state': stop['state'],
                    'cost': round(stop['cost_at_stop'], 2),
                    'cumulative_cost': round(cumulative, 2),
                    'price_per_gallon': stop['price_per_gallon'],
                    'gallons': stop['gallons_purchased'],
                    'miles_in': stop['miles_into_trip'],
                })

            response_data = {
                "success": True,
                "processing_time_seconds": elapsed,
                "trip": {
                    "start": {"input": start, "display_name": start_geo['display_name'],
                        "coordinates": {"lat": start_geo['lat'], "lon": start_geo['lon']}},
                    "finish": {"input": finish, "display_name": finish_geo['display_name'],
                        "coordinates": {"lat": finish_geo['lat'], "lon": finish_geo['lon']}},
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
                "chart_data": chart_data,
                "map": {
                    "route_geometry": route_data['features'][0]['geometry'],
                    "start_marker": {"lat": start_geo['lat'], "lon": start_geo['lon'], "label": start_geo['display_name'], "type": "start"},
                    "end_marker": {"lat": finish_geo['lat'], "lon": finish_geo['lon'], "label": finish_geo['display_name'], "type": "end"},
                    "fuel_stop_markers": [
                        {"lat": s['lat'], "lon": s['lon'], "label": f"Stop {s['stop_number']}: {s['station_name']}", "price": s['price_per_gallon'], "type": "fuel_stop"}
                        for s in optimization['fuel_stops']
                    ],
                },
                "summary": RoutePlannerView._build_summary(total_distance, total_duration, optimization),
            }
            return Response(response_data, status=status.HTTP_200_OK)

        except ValueError as e:
            return Response({"success": False, "error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except requests.exceptions.RequestException as e:
            return Response({"success": False, "error": f"Routing service error: {str(e)}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except Exception as e:
            return Response({"success": False, "error": f"Internal error: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @staticmethod
    def _format_duration(seconds):
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        return f"{h}h {m}m" if h > 0 else f"{m}m"

    @staticmethod
    def _build_summary(distance, duration, optimization):
        h = int(duration // 3600)
        m = int((duration % 3600) // 60)
        return {
            "total_distance": f"{round(distance, 1)} miles",
            "driving_time": f"{h}h {m}m",
            "fuel_stops": optimization['number_of_stops'],
            "total_fuel_cost": f"${optimization['total_fuel_cost']}",
            "total_gallons": f"{optimization['total_gallons']} gallons",
            "you_save": f"${optimization['savings_vs_average']} vs average prices",
        }


class MapView(APIView):
    def get(self, request):
        from django.shortcuts import render
        return render(request, 'index.html')