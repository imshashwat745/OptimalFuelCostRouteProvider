class SameDestinationError(ValueError):
    pass

class GeocodingError(RuntimeError):
    pass

class RoutingError(RuntimeError):
    pass

class NoViableRouteError(RuntimeError):
    pass
