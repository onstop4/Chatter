from typing import Optional
from urllib.parse import parse_qs, unquote

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from chatter.models import Room, RoomAccessStatus, RoomParticipant, User


def extract_username(query_string: str) -> str:
    """
    Extracts username from query string (which would be used by an anonymous user to
    join with a specific username). Will return 'guest_' + the extracted username.
    """
    try:
        found_username = parse_qs(unquote(query_string)).get("guest")[0]
        return f"guest_{found_username}" if found_username else ""
    except (TypeError, UnicodeError):
        return ""


@database_sync_to_async
def get_access_status(room_number: str, user: User, username: str) -> RoomAccessStatus:
    """
    Returns a :py:class:`RoomAccessStatus` instance determining whether or not a user
    is allowed to join a room associated with a specific room number (if such a room
    exists).
    """
    return Room.objects.get_access_status(room_number, user, username)


@database_sync_to_async
def is_owner(room: Room, user: User) -> bool:
    """
    Returns whether or not a user is the owner of a room.
    """
    return room.owner == user


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
    Removes any record of partipant associated with specific room. Does this by
    deleting objects from RoomParticipant and returning whether or not anything was
    deleted.
    """
    # Index 0 of tuple returned by get_or_create indicates how many objects were
    # deleted.
    return bool(
        RoomParticipant.objects.filter(room=room.id, username=username).delete()[0]
    )


@database_sync_to_async
def ban_user(room: Room, user: User):
    """
    Add user to room's set of banned users.
    """
    if user.is_authenticated:
        room.banned_users.add(user)
        room.save()


@database_sync_to_async
def get_info_update(room: Room, kicked: Optional[list] = None) -> dict:
    """
    Returns information about room that can be sent to client as update. This info
    includes room name, room access type, room owner, and a list of the room's
    participants.

    An optional list of kicked users can be passed as an argument. These users will be
    excluded from the list of participants. This is so that users who are supposed to
    have been kicked won't show up as participants, even if
    :py:func:`remove_participant` hasn't been called yet.
    """
    room.refresh_from_db()
    update = {
        "update": "info",
        "name": room.name,
        "access type": room.access_type,
        "owner": room.owner.username,
        "participants": get_participants(room),
    }
    if kicked:
        update["participants"] = [
            participant
            for participant in update["participants"]
            if participant not in kicked
        ]
    return update


def get_participants(room: Room) -> list[str]:
    """
    Returns list of room participants.
    """
    return list(
        room.participants.values_list("username", flat=True).order_by("username")
    )


@database_sync_to_async
def change_room_name(room: Room, name: str):
    """
    Changes room name.
    """
    room.name = name
    room.save()


@database_sync_to_async
def change_room_access_type(room: Room, access_type: str) -> list:
    """
    Changes room access type. Returns a list of room participants to be kicked as a
    result of the access type change.
    """
    room.access_type = access_type
    room.save()

    if access_type == "CONFIRMED":
        guests = room.participants.filter(username__startswith="guest_")
        return list(guests.values_list("username", flat=True))

    elif access_type == "PRIVATE":
        participants = list(room.participants.values_list("username", flat=True))
        invited = list(room.invited_users.values_list("username", flat=True))
        return [
            participant for participant in participants if participant not in invited
        ]

    return []


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
                self.is_owner = await is_owner(self.room, self.user)
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

        This method might have to be called manually due to this bug:
        https://github.com/django/channels/issues/1466
        """
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)
        await remove_participant(self.room, self.username)

    async def receive_json(self, content, **kwargs):
        """
        Performs actions as requested by the action key of the incoming JSON.
        """
        action = content.get("action")

        if action == "send message":
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "chat_message",
                    "message": str(content.get("message", "")),
                    "username": self.username,
                },
            )

        elif action == "get info":
            await self.send_json(await get_info_update(self.room))

        elif action == "change room name":
            if (new_name := str(content.get("name", ""))) and new_name.strip():
                await change_room_name(self.room, content)
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {"type": "chat_room_name_change", "name": new_name},
                )

        elif action == "change room access type":
            if (access_type := content.get("access type")) in [
                "PUBLIC",
                "CONFIRMED",
                "PRIVATE",
            ]:
                to_kick = await change_room_access_type(self.room, access_type)
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        "type": "chat_access_type_change",
                        "access type": access_type,
                        "kick": ", ".join(to_kick),
                    },
                )

        elif action == "kick user":
            if self.is_owner and (username_to_kick := str(content.get("username"))):
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {"type": "chat_kick", "username": username_to_kick},
                )

        elif action == "ban user":
            if (
                self.is_owner
                and (username_to_ban := str(content.get("username")))
                and not username_to_ban.startswith("guest_")
            ):
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {"type": "chat_ban", "username": username_to_ban},
                )

    async def chat_info(self, event):
        """
        Sends room info to client.
        """
        # pylint: disable=unused-argument
        await self.send_json(await get_info_update(self.room))

    async def chat_room_name_change(self, event):
        """
        Notifies client of room name change.
        """
        await self.send_json({"update": "name change", "name": event["name"]})

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

    async def chat_access_type_change(self, event):
        """
        If user is affected by room access change, then user will be kicked. If not,
        then user will be notified of room access change, the number of users who
        have been kicked, and the new room information.
        """
        to_kick = event["kick"].split(", ")
        if self.username in to_kick:
            await self.disconnect(None)
            await self.send_json(
                {
                    "update": "kicked you because access change",
                    "access type": event["access type"],
                },
                True,
            )
        else:
            await self.send_json(
                {
                    "update": "users kicked because access change",
                    "access type": event["access type"],
                    "quantity": len(to_kick),
                }
            )
            await self.send_json(await get_info_update(self.room, to_kick))

    async def chat_kick(self, event):
        """
        Receives event to kick a specific user. If said user is associated with client,
        alert client of this, close the connection, and remove user as participant. If
        not, just alert client that another user was kicked.
        """
        if event["username"] == self.username:
            await self.disconnect(None)
            await self.send_json({"update": "kicked you"}, True)
        else:
            await self.send_json(
                {"update": "user kicked", "username": event["username"]}
            )

    async def chat_ban(self, event):
        """
        Receives event to ban a specific user. If said user is associated with client,
        then ban said user, alert client of this, close the connection, and remove user
        as participant. If not, just alert client that another user was banned.
        """
        if event["username"] == self.username:
            await ban_user(self.room, self.user)
            await self.disconnect(None)
            await self.send_json({"update": "banned you"}, True)
        else:
            await self.send_json(
                {"update": "user banned", "username": event["username"]}
            )
