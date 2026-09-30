import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from routing.serializers import RouteRequestSerializer
from routing.map_service import MapService
from routing.fuel_algorithm import RouteOptimizer

logger = logging.getLogger(__name__)


class OptimalFuelRouteView(APIView):
    """
    POST /api/route/
    Calculates the driving route between two US locations, identifies optimal fuel stops
    based on lowest price within 500-mile tank range, and returns map GeoJSON.
    """
    def get(self, request):
        """
        Provides API documentation and instructions when accessed via GET in browsers.
        """
        return Response({
            "endpoint": "POST /api/route/",
            "description": "Calculates optimal driving route and cost-effective fuel stops across the USA.",
            "vehicle_parameters": {
                "max_range_miles": 500,
                "fuel_economy_mpg": 10
            },
            "sample_request_body": {
                "start": "New York, NY",
                "finish": "Los Angeles, CA"
            },
            "interactive_map": "/"
        }, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = RouteRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        start_loc = serializer.validated_data["start"]
        finish_loc = serializer.validated_data["finish"]

        try:
            # 1. Fetch route geometry and distance (single ORS call, cached)
            map_service = MapService()
            route_data = map_service.get_route(start_loc, finish_loc)

            # 2. Optimize fuel stops along the route (500-mile range, 10 MPG)
            optimizer = RouteOptimizer(route_data)
            optimization_result = optimizer.optimize_fuel_stops()

            # 3. Construct response with GeoJSON for interactive mapping
            response_data = {
                "route": {
                    "start": route_data["start"],
                    "finish": route_data["finish"],
                    "total_distance_miles": route_data["total_distance_miles"],
                    "duration_hours": round(route_data["duration_seconds"] / 3600.0, 2),
                    "geojson": route_data["geojson"]
                },
                "fuel_summary": {
                    "total_distance_miles": optimization_result["total_distance_miles"],
                    "total_gallons_consumed": optimization_result["total_gallons_consumed"],
                    "total_money_spent_usd": optimization_result["total_fuel_cost"],
                    "number_of_fuel_stops": optimization_result["number_of_stops"],
                    "vehicle_mpg": 10.0,
                    "max_tank_range_miles": 500.0
                },
                "fuel_stops": optimization_result["fuel_stops"]
            }

            return Response(response_data, status=status.HTTP_200_OK)

        except ValueError as ve:
            return Response({"error": str(ve)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.exception("Unexpected error calculating optimal fuel route")
            return Response({"error": f"Failed to compute route: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


from django.http import HttpResponse

MAP_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>FuelRoute &mdash; Smart Fuel Optimizer</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: 'Plus Jakarta Sans', sans-serif; display: flex; height: 100vh; width: 100vw; overflow: hidden; background: #0b0f19; color: #f1f5f9; }
        
        #sidebar {
            width: 440px;
            height: 100%;
            background: rgba(15, 23, 42, 0.94);
            backdrop-filter: blur(20px);
            border-right: 1px solid rgba(255, 255, 255, 0.08);
            display: flex;
            flex-direction: column;
            z-index: 1000;
            box-shadow: 10px 0 30px rgba(0,0,0,0.5);
            transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }

        .sidebar-header {
            padding: 24px 24px 16px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.06);
            display: flex;
            flex-direction: column;
            gap: 8px;
        }

        .brand-badge {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: rgba(14, 165, 233, 0.12);
            color: #38bdf8;
            padding: 4px 10px;
            border-radius: 999px;
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 0.5px;
            text-transform: uppercase;
            width: fit-content;
            border: 1px solid rgba(14, 165, 233, 0.25);
        }

        .brand-title {
            font-size: 22px;
            font-weight: 800;
            color: #ffffff;
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .brand-title span {
            background: linear-gradient(135deg, #38bdf8 0%, #818cf8 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .sidebar-scroll {
            flex: 1;
            overflow-y: auto;
            padding: 20px 24px;
            display: flex;
            flex-direction: column;
            gap: 20px;
        }

        .sidebar-scroll::-webkit-scrollbar { width: 6px; }
        .sidebar-scroll::-webkit-scrollbar-track { background: transparent; }
        .sidebar-scroll::-webkit-scrollbar-thumb { background: rgba(255, 255, 255, 0.15); border-radius: 4px; }

        /* Presets */
        .presets-title { font-size: 11px; text-transform: uppercase; color: #64748b; font-weight: 700; letter-spacing: 0.6px; margin-bottom: 8px; }
        .presets-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
        .preset-btn {
            background: rgba(30, 41, 59, 0.8);
            border: 1px solid rgba(255, 255, 255, 0.08);
            color: #cbd5e1;
            padding: 8px 10px;
            border-radius: 8px;
            font-size: 12px;
            font-weight: 600;
            cursor: pointer;
            text-align: left;
            transition: all 0.2s;
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .preset-btn:hover {
            background: rgba(14, 165, 233, 0.15);
            border-color: rgba(14, 165, 233, 0.4);
            color: #38bdf8;
            transform: translateY(-1px);
        }

        /* Input Form */
        .route-form { display: flex; flex-direction: column; gap: 12px; background: rgba(30, 41, 59, 0.5); padding: 16px; border-radius: 12px; border: 1px solid rgba(255, 255, 255, 0.06); }
        .input-group { display: flex; flex-direction: column; gap: 6px; position: relative; }
        .input-label { font-size: 11px; font-weight: 700; text-transform: uppercase; color: #94a3b8; letter-spacing: 0.5px; display: flex; align-items: center; gap: 6px; }
        .input-box {
            width: 100%;
            padding: 12px 14px;
            border-radius: 8px;
            border: 1px solid rgba(255, 255, 255, 0.1);
            background: #090d16;
            color: #f8fafc;
            font-size: 14px;
            font-family: inherit;
            font-weight: 500;
            outline: none;
            transition: all 0.2s;
        }
        .input-box:focus { border-color: #38bdf8; box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.15); }
        
        .swap-container { display: flex; justify-content: center; margin: -6px 0; }
        .swap-btn {
            background: #1e293b;
            border: 1px solid rgba(255, 255, 255, 0.12);
            color: #94a3b8;
            width: 32px;
            height: 32px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            transition: all 0.2s;
        }
        .swap-btn:hover { color: #38bdf8; border-color: #38bdf8; transform: rotate(180deg); }

        .submit-btn {
            background: linear-gradient(135deg, #0284c7 0%, #2563eb 100%);
            color: #ffffff;
            padding: 14px;
            border: none;
            border-radius: 10px;
            font-size: 14px;
            font-weight: 700;
            cursor: pointer;
            transition: all 0.2s;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            box-shadow: 0 4px 15px rgba(2, 132, 199, 0.35);
        }
        .submit-btn:hover { transform: translateY(-1px); box-shadow: 0 6px 20px rgba(2, 132, 199, 0.5); }
        .submit-btn:disabled { opacity: 0.6; cursor: not-allowed; }

        /* Loader */
        .loading-bar { display: none; text-align: center; color: #38bdf8; font-size: 13px; font-weight: 600; padding: 10px; }

        /* Summary Cards */
        .stats-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
        .stat-card {
            background: rgba(30, 41, 59, 0.6);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 10px;
            padding: 12px 14px;
            position: relative;
            overflow: hidden;
        }
        .stat-card::before {
            content: '';
            position: absolute;
            top: 0; left: 0;
            width: 3px; height: 100%;
            background: #38bdf8;
        }
        .stat-card.accent-emerald::before { background: #10b981; }
        .stat-card.accent-amber::before { background: #f59e0b; }
        .stat-card.accent-indigo::before { background: #818cf8; }

        .stat-label { font-size: 11px; text-transform: uppercase; color: #94a3b8; font-weight: 700; letter-spacing: 0.4px; }
        .stat-val { font-size: 20px; font-weight: 800; color: #f8fafc; margin-top: 4px; }
        .stat-sub { font-size: 11px; color: #64748b; margin-top: 2px; }

        /* Stops Section */
        .stops-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
        .stops-title { font-size: 14px; font-weight: 700; color: #f8fafc; }
        .stops-badge { background: rgba(16, 185, 129, 0.15); color: #10b981; padding: 3px 8px; border-radius: 6px; font-size: 11px; font-weight: 700; }

        .stops-list { display: flex; flex-direction: column; gap: 10px; }
        .stop-item {
            background: rgba(15, 23, 42, 0.8);
            border: 1px solid rgba(255, 255, 255, 0.07);
            border-radius: 10px;
            padding: 14px;
            cursor: pointer;
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
            position: relative;
        }
        .stop-item:hover {
            border-color: #10b981;
            background: rgba(16, 185, 129, 0.05);
            transform: translateX(4px);
        }
        .stop-item-top { display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; }
        .stop-name { font-size: 14px; font-weight: 700; color: #ffffff; }
        .stop-price-tag {
            background: rgba(16, 185, 129, 0.2);
            color: #34d399;
            font-size: 13px;
            font-weight: 800;
            padding: 3px 8px;
            border-radius: 6px;
            white-space: nowrap;
            border: 1px solid rgba(16, 185, 129, 0.3);
        }
        .stop-loc { font-size: 12px; color: #94a3b8; margin: 4px 0 8px; }
        .stop-meta { display: flex; justify-content: space-between; font-size: 11px; color: #64748b; border-top: 1px solid rgba(255, 255, 255, 0.05); padding-top: 8px; }
        .stop-meta b { color: #cbd5e1; }

        #map { flex: 1; height: 100%; position: relative; }

        /* Custom Leaflet Pin Badges */
        .custom-pin {
            width: 30px;
            height: 30px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-weight: 800;
            font-size: 13px;
            box-shadow: 0 4px 10px rgba(0,0,0,0.5);
            border: 2px solid white;
        }
        .pin-start { background: #0284c7; }
        .pin-finish { background: #ef4444; }
        .pin-fuel { background: #10b981; }
    </style>
</head>
<body>
    <div id="sidebar">
        <div class="sidebar-header">
            
            <div class="brand-title">FuelRoute <span></span></div>
            <div style="font-size: 12px; color: #64748b;">500-Mile Tank Range &bull; 10 MPG &bull; Cost-Optimal Routing</div>
        </div>

        <div class="sidebar-scroll">
            <!-- Quick Presets -->
            <div>
                <div class="presets-title">Quick Test Presets (1-Click)</div>
                <div class="presets-grid">
                    <button class="preset-btn" onclick="applyPreset('New York, NY', 'Los Angeles, CA')">&#128509; NYC &rarr; LA</button>
                    <button class="preset-btn" onclick="applyPreset('Dallas, TX', 'Denver, CO')">&#129312; Dallas &rarr; Denver</button>
                    <button class="preset-btn" onclick="applyPreset('Miami, FL', 'Seattle, WA')">&#127796; Miami &rarr; Seattle</button>
                    <button class="preset-btn" onclick="applyPreset('Philadelphia, PA', 'New York, NY')">&#128276; Philly &rarr; NYC</button>
                </div>
            </div>

            <!-- Route Inputs -->
            <div class="route-form">
                <div class="input-group">
                    <label class="input-label">&#128205; Origin</label>
                    <input id="start" class="input-box" value="New York, NY" placeholder="City, State" />
                </div>
                <div class="swap-container">
                    <button class="swap-btn" title="Swap start and finish" onclick="swapLocations()">&#8645;</button>
                </div>
                <div class="input-group">
                    <label class="input-label">&#127937; Destination</label>
                    <input id="finish" class="input-box" value="Los Angeles, CA" placeholder="City, State" />
                </div>
                <button id="submitBtn" class="submit-btn" onclick="calculateRoute()">
                    <span>Optimize Route &amp; Fuel Stops</span>
                </button>
            </div>

            <div id="loading" class="loading-bar">Computing route &amp; selecting lowest-priced stations...</div>

            <!-- Results Section -->
            <div id="results" style="display: none; flex-direction: column; gap: 16px;">
                <div class="stats-grid">
                    <div class="stat-card">
                        <div class="stat-label">Total Distance</div>
                        <div class="stat-val" id="stat-dist">--</div>
                        <div class="stat-sub" id="stat-time">-- hrs</div>
                    </div>
                    <div class="stat-card accent-emerald">
                        <div class="stat-label">Total Fuel Cost</div>
                        <div class="stat-val" id="stat-cost">--</div>
                        <div class="stat-sub">Lowest Price Path</div>
                    </div>
                    <div class="stat-card accent-amber">
                        <div class="stat-label">Fuel Stops</div>
                        <div class="stat-val" id="stat-stops">--</div>
                        <div class="stat-sub">&le; 500 mi per stop</div>
                    </div>
                    <div class="stat-card accent-indigo">
                        <div class="stat-label">Total Fuel</div>
                        <div class="stat-val" id="stat-fuel">--</div>
                        <div class="stat-sub">@ 10.0 MPG</div>
                    </div>
                </div>

                <div>
                    <div class="stops-header">
                        <span class="stops-title">Optimal Refueling Stops</span>
                        <span class="stops-badge" id="stops-badge">0 Stops</span>
                    </div>
                    <div class="stops-list" id="stops-list"></div>
                </div>
            </div>
        </div>
    </div>

    <div id="map"></div>

    <script>
        // Initialize Map with Esri World Navigation Tiles
        const map = L.map('map', { zoomControl: true }).setView([39.8283, -98.5795], 4);
        L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}', {
            attribution: 'Tiles &copy; Esri &mdash; Source: Esri, DeLorme, NAVTEQ, USGS, TomTom',
            maxZoom: 19
        }).addTo(map);

        let routeLayer = null;
        let markers = [];

        function applyPreset(start, finish) {
            document.getElementById('start').value = start;
            document.getElementById('finish').value = finish;
            calculateRoute();
        }

        function swapLocations() {
            const startElem = document.getElementById('start');
            const finishElem = document.getElementById('finish');
            const temp = startElem.value;
            startElem.value = finishElem.value;
            finishElem.value = temp;
            calculateRoute();
        }

        function focusMarker(idx) {
            if (markers[idx]) {
                map.flyTo(markers[idx].getLatLng(), 8, { duration: 1 });
                markers[idx].openPopup();
            }
        }

        async function calculateRoute() {
            const start = document.getElementById('start').value.trim();
            const finish = document.getElementById('finish').value.trim();
            const btn = document.getElementById('submitBtn');
            const loading = document.getElementById('loading');
            const results = document.getElementById('results');

            if (!start || !finish) {
                alert('Please provide both Start and Finish locations.');
                return;
            }

            btn.disabled = true;
            loading.style.display = 'block';
            results.style.display = 'none';

            if (routeLayer) map.removeLayer(routeLayer);
            markers.forEach(m => map.removeLayer(m));
            markers = [];

            try {
                const response = await fetch('/api/route/', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ start, finish })
                });

                const data = await response.json();
                loading.style.display = 'none';
                btn.disabled = false;

                if (!response.ok) {
                    alert('Error: ' + (data.error || JSON.stringify(data)));
                    return;
                }

                results.style.display = 'flex';
                const s = data.fuel_summary;

                // Populate metrics
                document.getElementById('stat-dist').innerText = s.total_distance_miles.toLocaleString() + ' mi';
                document.getElementById('stat-time').innerText = data.route.duration_hours + ' hrs driving';
                document.getElementById('stat-cost').innerText = '$' + s.total_money_spent_usd.toFixed(2);
                document.getElementById('stat-stops').innerText = s.number_of_fuel_stops;
                document.getElementById('stat-fuel').innerText = s.total_gallons_consumed.toFixed(1) + ' gal';
                document.getElementById('stops-badge').innerText = s.number_of_fuel_stops + ' Stops';

                // Add Start Pin
                const startIcon = L.divIcon({
                    className: 'custom-pin pin-start',
                    html: 'A',
                    iconSize: [28, 28],
                    iconAnchor: [14, 14]
                });
                const startPin = L.marker([data.route.start.lat, data.route.start.lon], { icon: startIcon }).addTo(map);
                startPin.bindPopup(`<b>Origin:</b> ${data.route.start.name}`);
                markers.push(startPin);

                // Add Fuel Stop Pins
                const stopsList = document.getElementById('stops-list');
                stopsList.innerHTML = '';

                if (data.fuel_stops.length === 0) {
                    stopsList.innerHTML = '<div style="color: #94a3b8; font-size: 13px; padding: 12px; background: rgba(30,41,59,0.5); border-radius: 8px;">No fuel stops needed. Trip is within single-tank range (&le; 500 miles).</div>';
                }

                data.fuel_stops.forEach((stop, idx) => {
                    const stopMarkerIndex = markers.length;

                    stopsList.innerHTML += `
                        <div class="stop-item" onmouseenter="focusMarker(${stopMarkerIndex})">
                            <div class="stop-item-top">
                                <div class="stop-name">#${idx + 1} ${stop.name}</div>
                                <div class="stop-price-tag">$${stop.price_per_gallon.toFixed(3)}/gal</div>
                            </div>
                            <div class="stop-loc">${stop.address ? stop.address + ', ' : ''}${stop.city}, ${stop.state}</div>
                            <div class="stop-meta">
                                <span>Refuel: <b>${stop.gallons_purchased} gal</b> ($${stop.cost.toFixed(2)})</span>
                                <span>Mile <b>${stop.mile_marker}</b></span>
                            </div>
                        </div>
                    `;

                    const fuelIcon = L.divIcon({
                        className: 'custom-pin pin-fuel',
                        html: (idx + 1),
                        iconSize: [26, 26],
                        iconAnchor: [13, 13]
                    });

                    const fuelPin = L.marker([stop.latitude, stop.longitude], { icon: fuelIcon }).addTo(map);
                    fuelPin.bindPopup(`
                        <div style="font-family: sans-serif; color: #0f172a; min-width: 170px;">
                            <div style="font-size: 11px; font-weight: 700; color: #10b981; text-transform: uppercase;">Stop #${idx + 1}</div>
                            <b style="font-size: 14px;">${stop.name}</b><br>
                            <span style="color: #64748b; font-size: 12px;">${stop.city}, ${stop.state}</span>
                            <div style="margin: 8px 0; padding: 6px 8px; background: #f0fdf4; border-radius: 6px; border: 1px solid #bbf7d0;">
                                <div style="color: #15803d; font-weight: 800; font-size: 16px;">$${stop.price_per_gallon.toFixed(3)} / gal</div>
                                <div style="color: #166534; font-size: 11px;">Buy: ${stop.gallons_purchased} gal ($${stop.cost.toFixed(2)})</div>
                            </div>
                            <div style="font-size: 11px; color: #94a3b8;">At Mile Marker: <b>${stop.mile_marker}</b></div>
                        </div>
                    `);
                    markers.push(fuelPin);
                });

                // Add Destination Pin
                const finishIcon = L.divIcon({
                    className: 'custom-pin pin-finish',
                    html: 'B',
                    iconSize: [28, 28],
                    iconAnchor: [14, 14]
                });
                const finishPin = L.marker([data.route.finish.lat, data.route.finish.lon], { icon: finishIcon }).addTo(map);
                finishPin.bindPopup(`<b>Destination:</b> ${data.route.finish.name}`);
                markers.push(finishPin);

                // Draw Route Polyline
                routeLayer = L.geoJSON(data.route.geojson, {
                    style: { color: '#0284c7', weight: 6, opacity: 0.9 }
                }).addTo(map);

                map.fitBounds(routeLayer.getBounds(), { padding: [60, 60] });

            } catch (err) {
                loading.style.display = 'none';
                btn.disabled = false;
                alert('Request failed: ' + err.message);
            }
        }

        // Auto-run on initial load
        window.addEventListener('DOMContentLoaded', () => {
            calculateRoute();
        });
    </script>
</body>
</html>"""


def map_view(request):
    return HttpResponse(MAP_HTML)

