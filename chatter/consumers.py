from urllib.parse import parse_qs, unquote

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from chatter.models import Room, RoomAccessStatus, RoomParticipant


def extract_username(query_string):
    try:
        found_username = parse_qs(unquote(query_string)).get("guest")[0]
        return f"guest_{found_username}" if found_username else ""
    except (TypeError, UnicodeError):
        return ""


@database_sync_to_async
def get_access_status(room_number, user, username):
    return Room.objects.get_access_status(room_number, user, username)


@database_sync_to_async
def add_participant(room: Room, username: str) -> bool:
    """
    Attempts to add record of participant to RoomParticipant. Will return True if added
    successfully. Will return False if existing recording was found.
    """
    # Index 1 of tuple returned by get_or_create indicates whether or not object was
    # created.
    return RoomParticipant.objects.get_or_create(
        room__id=room.id,
        username=username,
        defaults={"room": room, "username": username},
    )[1]


@database_sync_to_async
def remove_participant(room: Room, username: str) -> bool:
    """
    Rempves any record of partipant associated with specific Room. Does this by
    deleting objects from RoomParticipant and returning whether or not anything was
    deleted.
    """
    # Index 0 of tuple returned by get_or_create indicates how many objects were
    # deleted.
    return bool(
        RoomParticipant.objects.filter(room=room.id, username=username).delete()[0]
    )


@database_sync_to_async
def get_participants(room: Room) -> list[str]:
    """
    Returns list of room participants.
    """
    return list(
        room.participants.values_list("username", flat=True).order_by("username")
    )


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

        self.room, access_status = await get_access_status(
            self.room_number, self.user, self.username
        )
        if access_status == RoomAccessStatus.ALLOWED:
            if await add_participant(self.room, self.username):
                await self.accept()
                await self.send_json(
                    {
                        "update": "joined successfully",
                        "joined as": self.username,
                    }
                )
                await self.channel_layer.group_add(
                    self.room_group_name, self.channel_name
                )
            else:
                await self.close(RoomAccessStatus.ALREADY_JOINED.value)
        else:
            await self.close(access_status.value)

    async def disconnect(self, code):
        """
        Removes channel from group and records that user is no longer participant in
        room.
        """
        await remove_participant(self.room, self.username)
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        """
        Performs actions as requested by the action key of the incoming JSON.
        """
        action = content.get("action")

        if action == "get participants":
            await self.send_json(await get_participants(self.room))
        elif action == "send message":
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "chat_message",
                    "message": content.get("message", ""),
                    "username": self.username,
                },
            )

    async def chat_message(self, event):
        """
        Receives new chat message from room group and sends it to client (along with
        the username associated with the message).
        """
        await self.send_json(
            {
                "update": "new message",
                "message": event["message"],
                "username": event["username"],
            }
        )
