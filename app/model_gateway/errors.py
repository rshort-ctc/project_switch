class ModelGatewayError(RuntimeError):
    pass


class ModelGatewayConnectionError(ModelGatewayError):
    pass


class ModelGatewayResponseError(ModelGatewayError):
    pass


class ModelNotConfiguredError(ModelGatewayError):
    pass


class RerankingNotAvailableError(ModelGatewayError):
    pass
