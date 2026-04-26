from django.urls import path
from .views import (
    HealthCheckView,
    FuelStatsView,
    CheapestFuelByStateView,
    FuelPriceRankingView,
    RoutePlannerView,
    MapView,
)

urlpatterns = [
    path('', MapView.as_view(), name='map-view'),
    path('health/', HealthCheckView.as_view(), name='health-check'),
    path('fuel-stats/', FuelStatsView.as_view(), name='fuel-stats'),
    path('fuel-by-state/', CheapestFuelByStateView.as_view(), name='fuel-by-state'),
    path('fuel-ranking/', FuelPriceRankingView.as_view(), name='fuel-ranking'),
    path('route/', RoutePlannerView.as_view(), name='route-planner'),
]