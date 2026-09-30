# 🚗⛽ Fuel Route Optimizer API

A high-performance Django REST API that calculates driving routes across the USA and finds the most cost-effective fuel stops based on retail fuel prices, vehicle range, and fuel economy.

Built for the **Backend Django Engineer Assessment** at **Spotter**.

---

## 🌟 Key Features

* **Cost-Optimal Fuel Stops:** Selects the cheapest gas stations along the highway while respecting the **500-mile vehicle range constraint**.
* **10 MPG Fuel Math:** Accurately computes gallons consumed and total money spent on fuel.
* **Lightning Fast (<500ms):** Employs spatial 3D `scipy.spatial.KDTree` indexing over 8,000+ truck stops for sub-millisecond proximity queries.
* **Minimal API Footprint:** Exactly **1 API call** per route to OpenRouteService (ORS), backed by Django's in-memory cache to ensure repeated queries execute in **<10ms with 0 external API calls**.
* **Dual Interface:**
  * **REST API:** `POST /api/route/` returning structured GeoJSON, fuel stop details, and summary metrics.
  * **Interactive Map UI:** Built-in Leaflet.js interactive web map at `/` for visual validation.

---

## 🏗️ Architecture & Technical Decisions

| Requirement | Implementation & Design Decision |
|---|---|
| **Django Version** | Latest stable Django (6.1.1) + Django REST Framework |
| **Routing Provider** | OpenRouteService (ORS) Directions API (`driving-car`) |
| **API Call Efficiency** | 1 single ORS call fetches distance and complete route polyline; cached for 24h via `LocMemCache` |
| **Fuel Data Geocoding** | Enriched offline with US Census city coordinates into `fuel_stops_with_coords.csv` — **zero runtime geocoding API calls** |
| **Spatial Proximity** | `scipy.spatial.KDTree` on 3D Cartesian spherical coordinates ($O(\log N)$ query speed) |
| **Optimization Strategy** | Greedy cost-minimization within a dynamic refueling window (between 300 and 485 miles driven) to prevent premature stopping and minimize total fuel expenditure |

---

## 🚀 Quickstart Guide

### 1. Prerequisites & Environment Setup

```bash
# Clone the repository
git clone <your-github-repo-url>
cd fuel-route-ap

# Create and activate virtual environment
python -m venv venv
# On Windows PowerShell:
.\venv\Scripts\Activate.ps1
# On Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install django djangorestframework requests pandas scipy
```

### 2. Configuration

Create `api.txt` in the root folder containing your OpenRouteService API key (or set `ORS_API_KEY` environment variable):

```text
<your-openrouteservice-api-key>
```

### 3. Run Migrations & Start Server

```bash
python manage.py migrate
python manage.py runserver
```

The server will be live at `http://127.0.0.1:8000/`.

---

## 📡 API Reference

### Calculate Optimal Fuel Route

**`POST /api/route/`**

#### Request Headers
```http
Content-Type: application/json
```

#### Request Body
```json
{
  "start": "New York, NY",
  "finish": "Los Angeles, CA"
}
```

#### Response (`200 OK`)
```json
{
  "route": {
    "start": { "name": "New York, NY", "lat": 40.7128, "lon": -74.006 },
    "finish": { "name": "Los Angeles, CA", "lat": 34.0522, "lon": -118.2437 },
    "total_distance_miles": 2797.98,
    "duration_hours": 41.5,
    "geojson": {
      "type": "Feature",
      "geometry": { "type": "LineString", "coordinates": [[-74.006, 40.7128], ...] }
    }
  },
  "fuel_summary": {
    "total_distance_miles": 2797.98,
    "total_gallons_consumed": 279.8,
    "total_money_spent_usd": 768.96,
    "number_of_fuel_stops": 6,
    "vehicle_mpg": 10.0,
    "max_tank_range_miles": 500.0
  },
  "fuel_stops": [
    {
      "truckstop_id": "36",
      "name": "SHENANDOAH TRUCK CENTER",
      "address": "I-81, EXIT 273 & SR-703/SR-292",
      "city": "Mount Jackson",
      "state": "VA",
      "latitude": 38.7688,
      "longitude": -78.6766,
      "price_per_gallon": 2.899,
      "mile_marker": 384.2,
      "gallons_purchased": 38.42,
      "cost": 111.38
    }
    // ...
  ]
}
```

---

## 🗺️ Interactive Web Interface

Visit **`http://127.0.0.1:8000/`** in any web browser to view the interactive Leaflet map interface:
* Visualizes the driving route polyline.
* Displays green pins for each selected cost-optimal fuel station with popup pricing details.
* Shows a breakdown of total distance, gallons consumed, and money spent.
