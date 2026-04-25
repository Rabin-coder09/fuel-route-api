from django.urls import path
from .views import (
    HealthCheckView,
    FuelStatsView,
    CheapestFuelByStateView,
    RoutePlannerView,
)

urlpatterns = [
    path('health/', HealthCheckView.as_view(), name='health-check'),
    path('fuel/stats/', FuelStatsView.as_view(), name='fuel-stats'),
    path('fuel/by-state/', CheapestFuelByStateView.as_view(), name='fuel-by-state'),
    path('route/', RoutePlannerView.as_view(), name='route-planner'),
]