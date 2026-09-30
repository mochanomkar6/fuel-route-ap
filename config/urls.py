from django.contrib import admin
from django.urls import path, include
from routing.views import map_view

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('routing.urls')),
    path('', map_view, name='map-interface'),
]

