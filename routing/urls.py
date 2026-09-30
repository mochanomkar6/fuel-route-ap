from django.urls import path
from routing.views import OptimalFuelRouteView

urlpatterns = [
    path('route/', OptimalFuelRouteView.as_view(), name='optimal-fuel-route'),
]
