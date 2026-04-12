from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('spotter.urls')), # This routes anything starting with /api/ to your app
]