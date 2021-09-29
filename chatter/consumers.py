from urllib.parse import parse_qs, unquote

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from chatter.models import Room, RoomAccessStatus


def extract_username(query_string):
    try:
        found_username = parse_qs(unquote(query_string)).get("guest")[0]
        return f"guest_{found_username}" if found_username else ""
    except (TypeError, UnicodeError):
        return ""


@database_sync_to_async
def get_access_status(room_number, user, username):
    return Room.objects.get_access_status(room_number, user, username)


class ChatConsumer(AsyncJsonWebsocketConsumer):
    """
    Handles chatroom communication.
    """

    async def connect(self):
        """
        Accepts user connections. If user isn't allowed to join room, a response will
        be sent explaining the reason why, and the connection will be closed.
        If the user is allowed to join, they will be sent a response containing their
        username for the room, and their channel will be added to the room's group.
        """
        self.room_number = self.scope["url_route"]["kwargs"]["room_number"]
        self.room_group_name = f"chat_{self.room_number}"
        self.user = self.scope["user"]

        # Use guest username if user is not logged in.
        self.username = (
            self.user.username
            if self.user.is_authenticated
            else extract_username(self.scope["query_string"])
        )

        await self.accept()
        self.room, access_status = await get_access_status(
            self.room_number, self.user, self.username
        )
        if access_status == RoomAccessStatus.ALLOWED:
            await self.send_json(
                {
                    "update": "join status",
                    "status": access_status.value,
                    "joined as": self.username,
                }
            )
        else:
            await self.send_json(
                {"update": "join status", "status": access_status.value}, True
            )
            return
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)

    async def disconnect(self, code):
        """
        Removes channel from group.
        """
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)
