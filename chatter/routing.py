from django.urls import re_path

from chatter import consumers

websocket_urlpatterns = [
    re_path(r"ws/chat/(?P<room_number>\w+)/$", consumers.ChatConsumer.as_asgi()),
]
