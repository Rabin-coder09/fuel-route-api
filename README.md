# 🚗 Fuel Route Optimizer API

[![Python](https://img.shields.io/badge/Python-3.11-blue)](https://python.org)
[![Django](https://img.shields.io/badge/Django-5.0-green)](https://djangoproject.com)
[![DRF](https://img.shields.io/badge/DRF-3.15-red)](https://django-rest-framework.org)
[![Tests](https://img.shields.io/badge/Tests-26%20Passed-brightgreen)](https://github.com/Rabin-coder09/fuel-route-api)

A production-ready Django REST API that plans the most cost-effective fuel stops for road trips across the USA. Built with Django 5.0, Django REST Framework, and OpenRouteService API.

---

## 🌟 Features

- ✅ Optimal fuel stop planning based on real fuel prices from 8000+ stations
- ✅ 500-mile vehicle range with smart multi-stop strategy
- ✅ Interactive SVG map with route visualization and clickable
fuel stop markers
- ✅ Cost calculation at 10 MPG with savings vs average prices
- ✅ Alternative fuel stations shown at each stop
- ✅ Full route geometry for map visualization
- ✅ Smart caching - repeat requests served instantly
- ✅ Auto API docs via Swagger UI and ReDoc
- ✅ 26 unit tests with 100% pass rate
- ✅ Production ready with throttling, CORS, and error handling
- ✅ Single ORS API call per unique route - extremely efficient

---

## 🚀 Quick Start

### 1. Clone and Setup

```bash
git clone https://github.com/Rabin-coder09/fuel-route-api.git
cd fuel-route-api
conda create -n fuelapi python=3.11
conda activate fuelapi
pip install -r requirements.txt
```

### 2. Environment Variables

Create a `.env` file in the project root:

```env
ORS_API_KEY=your_openrouteservice_api_key
DEBUG=True
SECRET_KEY=your-secret-key
ALLOWED_HOSTS=*
```

### 3. Run the Server

```bash
python manage.py migrate
python manage.py runserver
```

API runs at http://127.0.0.1:8000

Docs at http://127.0.0.1:8000/api/docs/

---

## 📡 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health/` | Health check and system status |
| GET | `/api/fuel-stats/` | Fuel price statistics across USA |
| GET | `/api/fuel-by-state/?state=TX` | Cheapest stations by state |
| GET | `/api/route/?start=...&finish=...` | Plan optimal fuel route |
| GET | `/api/docs/` | Swagger UI documentation |
| GET | `/api/redoc/` | ReDoc documentation |
| GET | `/api/schema/` | OpenAPI 3.0 schema |

---
## 🗺️ Interactive Web Interface

Visit `http://127.0.0.1:8000` in your browser for the full interactive experience:

- **Route Map** — Plan route and see fuel stops on live map
- **Price Heatmap** — See fuel prices across all USA states
- **State Rankings** — Compare cheapest states for fuel
- **Quick Routes** — One-click popular US routes
- **Tank Level Indicator** — See fuel level at each stop
- **Nearby Alternatives** — Compare stations at each stop

## 🗺️ Route Planner Usage

### Request

```
GET /api/route/?start=New York, NY&finish=Los Angeles, CA
```

### Sample Response

```json
{
    "success": true,
    "processing_time_seconds": 4.38,
    "trip": {
        "start": {
            "display_name": "New York, NY, USA",
            "coordinates": {
                "lat": 40.68,
                "lon": -73.97
            }
        },
        "finish": {
            "display_name": "Los Angeles, CA, USA",
            "coordinates": {
                "lat": 34.05,
                "lon": -118.25
            }
        },
        "distance_miles": 2797.2,
        "estimated_duration": "45h 1m"
    },
    "fuel_optimization": {
        "number_of_stops": 5,
        "total_fuel_cost_usd": 871.95,
        "total_gallons_needed": 279.71,
        "average_price_per_gallon": 3.117,
        "estimated_savings_vs_avg_usd": 288.60,
        "fuel_stops": [
            {
                "stop_number": 1,
                "station_name": "SHEETZ #683",
                "city": "York",
                "state": "PA",
                "price_per_gallon": 3.259,
                "gallons_purchased": 40.62,
                "cost_at_stop": 132.37,
                "miles_into_trip": 406.2,
                "nearby_alternatives": []
            }
        ]
    },
    "summary": {
        "total_distance": "2797.2 miles",
        "driving_time": "45h 1m",
        "fuel_stops": 5,
        "total_fuel_cost": "$871.95",
        "you_save": "$288.60 vs average prices"
    }
}
```

---

## 🏗️ Architecture

```
fuel-route-api/
├── fuel_route/
│   ├── settings.py        All configuration and constants
│   └── urls.py            Main URL routing with docs
├── route_planner/
│   ├── services.py        Business logic layer
│   │   ├── FuelDataService      CSV loader using Singleton pattern
│   │   ├── GeocodingService     ORS geocoding with caching
│   │   ├── RouteService         ORS routing with single API call
│   │   └── FuelStopOptimizer    Haversine optimization algorithm
│   ├── views.py           REST API endpoints
│   ├── urls.py            App URL configuration
│   └── tests.py           26 unit and integration tests
├── fuel-prices-for-be-assessment.csv
├── .env
├── requirements.txt
└── README.md
```

---

## ⚡ Performance

| Metric | Value |
|--------|-------|
| First response | 4 to 10 seconds |
| Cached response | Under 0.1 seconds |
| Cache duration | 1 hour |
| API calls per route | 1 ORS Directions call only |
| Test suite speed | 26 tests in 0.161 seconds |

---

## 💡 Optimization Algorithm

1. **Geocode** start and finish locations using ORS geocoding API
2. **Fetch** full route geometry with a single ORS Directions API call
3. **Sample** route coordinates at regular intervals along the path
4. **Every 400 miles** search for fuel stations within 150 mile radius
5. **Haversine formula** calculates exact distances to all nearby stations
6. **Select cheapest** station at each stop window
7. **Calculate** gallons needed and cost at each stop
8. **Return** full breakdown with alternatives and total savings

---

## 🧪 Testing

```bash
python manage.py test
```

```
Ran 26 tests in 0.161s
OK
```

| Test Class | Tests | Coverage |
|------------|-------|----------|
| HealthCheckView | 4 | Status, database, vehicle settings |
| FuelStatsView | 3 | Response format and price validation |
| CheapestFuelByStateView | 5 | Valid and invalid states, case handling |
| RoutePlannerView | 4 | Validation and response structure |
| FuelStopOptimizer | 4 | Haversine formula and state coordinates |
| FuelDataService | 5 | Singleton pattern and data loading |

---

## 🔧 Tech Stack

| Technology | Purpose |
|------------|---------|
| Django 5.0 | Web framework |
| Django REST Framework | API toolkit |
| drf-spectacular | Swagger and ReDoc documentation |
| OpenRouteService API | Routing and geocoding |
| Pandas | Fuel CSV data processing |
| django-cors-headers | CORS support |
| python-dotenv | Environment variable management |
| Django Cache Framework | In-memory caching layer |

---

## 📄 License

MIT License - feel free to use this project!