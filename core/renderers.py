from rest_framework.renderers import JSONRenderer


class UnifiedJSONRenderer(JSONRenderer):
    """
    Response format: {"message": "success", "data": ...}
    """

    def render(self, data, accepted_media_type=None, renderer_context=None):
        response = renderer_context.get("response")

        status_msg = "success"
        if response and response.status_code >= 400:
            status_msg = "error"

        unified_data = {"message": status_msg, "data": data}

        return super().render(unified_data, accepted_media_type, renderer_context)
