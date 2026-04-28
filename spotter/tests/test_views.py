"""
Tests for the API layer (views + serializers).

All external services are mocked — no network calls.
"""
from unittest.mock import patch
from django.test import TestCase
from rest_framework.test import APIRequestFactory
from spotter.api.views import RouteOptimizerView
from spotter.exceptions import (
    GeocodingError, NoViableRouteError, RoutingError, SameDestinationError,
)


class RouteOptimizerViewTests(TestCase):
    """Test API endpoint error handling and response structure."""

    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = RouteOptimizerView.as_view()

    def test_missing_start_param(self):
        request = self.factory.get("/api/route/", {"destination_address": "Denver, CO"})
        response = self.view(request)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"], "invalid_params")

    def test_missing_finish_param(self):
        request = self.factory.get("/api/route/", {"start_address": "Chicago, IL"})
        response = self.view(request)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"], "invalid_params")

    def test_missing_both_params(self):
        request = self.factory.get("/api/route/")
        response = self.view(request)
        self.assertEqual(response.status_code, 400)

    def test_negative_buffer_gallons(self):
        request = self.factory.get("/api/route/", {
            "start_address": "Chicago, IL",
            "destination_address": "Denver, CO",
            "buffer_gallons": "-1",
        })
        response = self.view(request)
        self.assertEqual(response.status_code, 400)

    @patch("spotter.api.views.calculate_cheapest_route")
    def test_same_destination_error(self, mock_route):
        mock_route.side_effect = SameDestinationError("Same place")
        request = self.factory.get("/api/route/", {
            "start_address": "Chicago, IL",
            "destination_address": "Chicago, IL",
        })
        response = self.view(request)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"], "same_destination")

    @patch("spotter.api.views.calculate_cheapest_route")
    def test_geocoding_error(self, mock_route):
        mock_route.side_effect = GeocodingError("Failed to geocode")
        request = self.factory.get("/api/route/", {
            "start_address": "Nonexistent Place",
            "destination_address": "Denver, CO",
        })
        response = self.view(request)
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.data["error"], "upstream_error")

    @patch("spotter.api.views.calculate_cheapest_route")
    def test_routing_error(self, mock_route):
        mock_route.side_effect = RoutingError("OSRM down")
        request = self.factory.get("/api/route/", {
            "start_address": "Chicago, IL",
            "destination_address": "Denver, CO",
        })
        response = self.view(request)
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.data["error"], "upstream_error")

    @patch("spotter.api.views.calculate_cheapest_route")
    def test_no_viable_route_error(self, mock_route):
        mock_route.side_effect = NoViableRouteError("No route found")
        request = self.factory.get("/api/route/", {
            "start_address": "Chicago, IL",
            "destination_address": "Denver, CO",
        })
        response = self.view(request)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.data["error"], "no_viable_route")

    @patch("spotter.api.views.calculate_cheapest_route")
    def test_internal_error(self, mock_route):
        mock_route.side_effect = RuntimeError("Something unexpected")
        request = self.factory.get("/api/route/", {
            "start_address": "Chicago, IL",
            "destination_address": "Denver, CO",
        })
        response = self.view(request)
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.data["error"], "internal_error")

    @patch("spotter.api.views.calculate_cheapest_route")
    def test_success_response_structure(self, mock_route):
        mock_route.return_value = {
            "route_option": 1,
            "total_distance_miles": 1002.54,
            "total_fuel_cost": 342.18,
            "fuel_stops": [],
            "route_geometry": {"type": "LineString", "coordinates": []},
        }
        request = self.factory.get("/api/route/", {
            "start_address": "Chicago, IL",
            "destination_address": "Denver, CO",
        })
        response = self.view(request)
        self.assertEqual(response.status_code, 200)
        self.assertIn("request", response.data)
        self.assertIn("optimal_trip", response.data)
        trip = response.data["optimal_trip"]
        self.assertIn("route_option", trip)
        self.assertIn("total_distance_miles", trip)
        self.assertIn("total_fuel_cost", trip)
        self.assertIn("fuel_stops", trip)
        self.assertIn("route_geometry", trip)

    @patch("spotter.api.views.calculate_cheapest_route")
    def test_default_params(self, mock_route):
        mock_route.return_value = {
            "route_option": 1,
            "total_distance_miles": 500.0,
            "total_fuel_cost": 100.0,
            "fuel_stops": [],
            "route_geometry": {"type": "LineString", "coordinates": []},
        }
        request = self.factory.get("/api/route/", {
            "start_address": "A",
            "destination_address": "B",
        })
        response = self.view(request)
        self.assertEqual(response.status_code, 200)
        # Verify defaults were applied
        req_data = response.data["request"]
        self.assertEqual(req_data["buffer_gallons"], 2.0)
        self.assertEqual(req_data["greedy_fill"], False)
