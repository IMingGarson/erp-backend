from rest_framework.views import exception_handler


def unified_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is not None:
        pass

    return response
