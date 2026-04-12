from django.urls import path
from .api.views import RouteOptimizerView

urlpatterns = [
    path("route/", RouteOptimizerView.as_view(), name="route-optimizer"),
]