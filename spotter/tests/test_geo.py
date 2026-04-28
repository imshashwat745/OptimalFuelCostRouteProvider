"""
Tests for spotter.utils.geo — calculate_haversine_distance and project_point_to_line_segment.
"""
from django.test import TestCase
from spotter.utils.geo import calculate_haversine_distance, project_point_to_line_segment, cumulative_distances_np
import math


class HaversineTests(TestCase):
    """Verify calculate_haversine_distance distance formula against known distances."""

    def test_same_point_returns_zero(self):
        self.assertAlmostEqual(calculate_haversine_distance(40.0, -74.0, 40.0, -74.0), 0.0, places=6)

    def test_known_distance_nyc_to_la(self):
        """NYC (40.7128, -74.0060) to LA (34.0522, -118.2437) ≈ 2,451 mi."""
        d = calculate_haversine_distance(40.7128, -74.0060, 34.0522, -118.2437)
        self.assertAlmostEqual(d, 2451, delta=15)

    def test_short_distance(self):
        """Two points ~1 mile apart at lat 40."""
        lat = 40.0
        # 1 degree of latitude ≈ 69.0 mi, so 1/69 degrees ≈ 1 mi
        d = calculate_haversine_distance(lat, -74.0, lat + 1 / 69.0, -74.0)
        self.assertAlmostEqual(d, 1.0, delta=0.05)

    def test_symmetry(self):
        d1 = calculate_haversine_distance(41.0, -87.0, 39.0, -104.0)
        d2 = calculate_haversine_distance(39.0, -104.0, 41.0, -87.0)
        self.assertAlmostEqual(d1, d2, places=6)


class PointOnSegmentTests(TestCase):
    """Verify perpendicular distance and projection offset."""

    def test_project_point_to_line_segment_endpoint(self):
        """Point is exactly at the first endpoint — dist=0, offset=0."""
        dist, offset = project_point_to_line_segment(40.0, -74.0, 40.0, -74.0, 41.0, -74.0)
        self.assertAlmostEqual(dist, 0.0, delta=0.01)
        self.assertAlmostEqual(offset, 0.0, delta=0.01)

    def test_project_point_to_line_segment_midpoint(self):
        """Point at midpoint of a north-south segment."""
        dist, offset = project_point_to_line_segment(40.5, -74.0, 40.0, -74.0, 41.0, -74.0)
        seg_len = calculate_haversine_distance(40.0, -74.0, 41.0, -74.0)
        self.assertAlmostEqual(dist, 0.0, delta=0.1)
        self.assertAlmostEqual(offset, seg_len / 2, delta=0.5)

    def test_point_off_segment(self):
        """Point 1 degree east of a north-south segment."""
        dist, offset = project_point_to_line_segment(40.5, -73.0, 40.0, -74.0, 41.0, -74.0)
        # ~53 miles east at lat 40.5
        self.assertGreater(dist, 40)
        self.assertLess(dist, 60)

    def test_zero_length_segment(self):
        """Degenerate segment (both endpoints same) returns distance to the point."""
        dist, offset = project_point_to_line_segment(41.0, -74.0, 40.0, -74.0, 40.0, -74.0)
        self.assertAlmostEqual(offset, 0.0, places=6)
        self.assertGreater(dist, 60)  # ~69 mi for 1 degree


class CumulativeDistancesTests(TestCase):
    """Verify vectorized cumulative distance computation."""

    def test_two_points(self):
        coords = [(-74.0, 40.0), (-74.0, 41.0)]
        cum, total = cumulative_distances_np(coords)
        self.assertAlmostEqual(cum[0], 0.0)
        self.assertAlmostEqual(total, calculate_haversine_distance(40.0, -74.0, 41.0, -74.0), delta=0.01)

    def test_three_points_cumulative(self):
        coords = [(-74.0, 40.0), (-74.0, 41.0), (-74.0, 42.0)]
        cum, total = cumulative_distances_np(coords)
        d1 = calculate_haversine_distance(40.0, -74.0, 41.0, -74.0)
        d2 = calculate_haversine_distance(41.0, -74.0, 42.0, -74.0)
        self.assertAlmostEqual(cum[1], d1, delta=0.01)
        self.assertAlmostEqual(total, d1 + d2, delta=0.01)

    def test_matches_scalar_calculate_haversine_distance(self):
        """Vectorized result matches sequential scalar calls."""
        coords = [(-87.0, 41.0), (-90.0, 41.5), (-95.0, 40.0), (-104.0, 39.0)]
        cum, total = cumulative_distances_np(coords)
        expected_cum = 0.0
        for i in range(1, len(coords)):
            lon1, lat1 = coords[i - 1]
            lon2, lat2 = coords[i]
            expected_cum += calculate_haversine_distance(lat1, lon1, lat2, lon2)
            self.assertAlmostEqual(cum[i], expected_cum, delta=0.01)
        self.assertAlmostEqual(total, expected_cum, delta=0.01)
