import logging
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from ..api.serializers import RouteQuerySerializer
from ..exceptions import GeocodingError, NoViableRouteError, RoutingError, SameDestinationError
from ..services.route_service import get_optimal_route

logger = logging.getLogger(__name__)


class RouteOptimizerView(APIView):
    """
    GET /api/route/?start=Chicago,IL&finish=Denver,CO
    Optional: &buffer_gallons=5&greedy_fill=false
    """

    def get(self, request):
        serializer = RouteQuerySerializer(data=request.query_params)
        if not serializer.is_valid():
            return Response(
                {"error": "invalid_params", "details": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = serializer.validated_data

        try:
            result = get_optimal_route(
                data["start"],
                data["finish"],
                buffer_gallons=data["buffer_gallons"],
                greedy_fill=data["greedy_fill"],
            )
        except SameDestinationError as exc:
            return Response({"error": "same_destination", "message": str(exc)},
                            status=status.HTTP_400_BAD_REQUEST)
        except (GeocodingError, RoutingError) as exc:
            logger.warning("Upstream error: %s", exc)
            return Response({"error": "upstream_error", "message": str(exc)},
                            status=status.HTTP_502_BAD_GATEWAY)
        except NoViableRouteError as exc:
            return Response({"error": "no_viable_route", "message": str(exc)},
                            status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        except Exception:
            logger.exception("Unhandled error in RouteOptimizerView")
            return Response({"error": "internal_error", "message": "An unexpected error occurred."},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({
            "request": data,
            "optimal_trip": result,
        }, status=status.HTTP_200_OK)
