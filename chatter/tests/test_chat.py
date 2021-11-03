# from unittest import skip

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.testing import WebsocketCommunicator
from django.test import TransactionTestCase

from chatter.models import Room, User
import chatter.routing

application = ProtocolTypeRouter(
    {"websocket": AuthMiddlewareStack(URLRouter(chatter.routing.websocket_urlpatterns))}
)

TIMEOUT = 2


class ChatroomConnectionTests(TransactionTestCase):
    """
    Performs tests related to connecting and joining chat rooms.
    """

    def setUp(self):
        """
        Sets up environment for tests. This includes three users (one room owner, an
        "allowed" user, and a "bad" user). Three rooms are also created. The bad user
        is banned from the public and confirmed rooms and is not invited to the private
        room. The allowed user is not banned from any room, and they are invited to the
        private room.
        """
        self.owner = User.objects.create_user("owner", "owner@example.com", "12345")

        self.allowed_user = User.objects.create_user(
            "allowed_user", "allowed@example.com", "12345"
        )

        self.bad_user = User.objects.create_user(
            "banned_user", "banned@example.com", "12345"
        )

        self.public_room = Room.objects.create(
            name="Room", number="1234567890", owner=self.owner
        )
        self.public_room_websocket_url = f"/ws/chat/{self.public_room.number}/"
        self.public_room.banned_users.add(self.bad_user)
        self.public_room.save()

        self.confirmed_room = Room.objects.create(
            name="Room",
            number="2345678901",
            owner=self.owner,
            access_type=Room.AccessTypes.CONFIRMED,
        )
        self.confirmed_room_websocket_url = f"/ws/chat/{self.confirmed_room.number}/"
        self.confirmed_room.banned_users.add(self.bad_user)
        self.confirmed_room.save()

        self.private_room = Room.objects.create(
            name="Room",
            number="3456789012",
            owner=self.owner,
            access_type=Room.AccessTypes.PRIVATE,
        )
        self.private_room_websocket_url = f"/ws/chat/{self.private_room.number}/"
        self.private_room.invited_users.add(self.allowed_user)
        self.private_room.save()

    async def test_join_good_public(self):
        """
        Tests that users can join public rooms as long as they are not banned.
        """
        # Connect as allowed_user.
        communicator = WebsocketCommunicator(
            application, self.public_room_websocket_url
        )
        communicator.scope["user"] = self.allowed_user

        connected = (await communicator.connect())[0]
        self.assertTrue(connected)

        response = await communicator.receive_json_from(TIMEOUT)
        self.assertEqual(
            {
                "update": "joined successfully",
                "joined as": self.allowed_user.username,
            },
            response,
        )

        # Connect as anonymous user.
        communicator2 = WebsocketCommunicator(
            application, f"{self.public_room_websocket_url}?guest=test"
        )

        connected = (await communicator2.connect())[0]
        self.assertTrue(connected)

        response = await communicator2.receive_json_from(TIMEOUT)
        self.assertEqual(
            {"update": "joined successfully", "joined as": "guest_test"},
            response,
        )

    async def test_join_good_confirmed(self):
        """
        Tests that users can join confirmed rooms as long as they are not banned.
        """
        communicator = WebsocketCommunicator(
            application, self.confirmed_room_websocket_url
        )
        communicator.scope["user"] = self.allowed_user

        connected = (await communicator.connect())[0]
        self.assertTrue(connected)

        response = await communicator.receive_json_from(TIMEOUT)
        self.assertEqual(
            {
                "update": "joined successfully",
                "joined as": self.allowed_user.username,
            },
            response,
        )

    async def test_join_good_private(self):
        """
        Tests that users can join private rooms as long as they are invited.
        """
        communicator = WebsocketCommunicator(
            application, self.private_room_websocket_url
        )
        communicator.scope["user"] = self.allowed_user

        connected = (await communicator.connect())[0]
        self.assertTrue(connected)

        response = await communicator.receive_json_from(TIMEOUT)
        self.assertEqual(
            {
                "update": "joined successfully",
                "joined as": self.allowed_user.username,
            },
            response,
        )

    async def test_join_not_found(self):
        """
        Tests that connection is closed with proper error message when a room has not
        been found.
        """
        # Connect as allowed_user.
        communicator = WebsocketCommunicator(application, "/ws/chat/54321/")
        communicator.scope["user"] = self.allowed_user

        connected, code = await communicator.connect()
        self.assertFalse(connected)
        self.assertEqual(4001, code)

        # Connect as anonymous user.
        communicator2 = WebsocketCommunicator(application, "/ws/chat/54321/")

        connected, code = await communicator2.connect()
        self.assertFalse(connected)
        self.assertEqual(4001, code)

    async def test_join_bad_username(self):
        """
        Tests that connection is closed with proper error message when guest user has a
        bad username.
        """
        # Username specified is space character.
        communicator = WebsocketCommunicator(
            application, f"{self.public_room_websocket_url}?guest=%20"
        )

        connected, code = await communicator.connect()
        self.assertFalse(connected)
        self.assertEqual(4002, code)

        # Username specified is blank.
        communicator2 = WebsocketCommunicator(
            application, f"{self.public_room_websocket_url}?guest="
        )

        connected, code = await communicator2.connect()
        self.assertFalse(connected)
        self.assertEqual(4002, code)

        # Username specified includes space character.
        communicator3 = WebsocketCommunicator(
            application, f"{self.public_room_websocket_url}?guest=test%20bad"
        )

        connected, code = await communicator3.connect()
        self.assertFalse(connected)
        self.assertEqual(4002, code)

        # No username is specified.
        communicator4 = WebsocketCommunicator(
            application, self.public_room_websocket_url
        )

        connected, code = await communicator4.connect()
        self.assertFalse(connected)
        self.assertEqual(4002, code)

    async def test_join_confirm_required(self):
        """
        Tests that connection is closed with proper error message when a guest user
        tries to join a confirmed room.
        """
        communicator = WebsocketCommunicator(
            application, f"{self.confirmed_room_websocket_url}?guest=test"
        )

        connected, code = await communicator.connect()
        self.assertFalse(connected)
        self.assertEqual(4003, code)

    async def test_join_not_invited(self):
        """
        Tests that connection is closed with proper error message when a normal user
        tries to join a private room that have not been invited to. Also tests that
        guest users will receive same error message when they try to join private
        rooms.
        """
        # Connect as allowed_user.
        communicator = WebsocketCommunicator(
            application, self.private_room_websocket_url
        )
        communicator.scope["user"] = self.bad_user

        connected, code = await communicator.connect()
        self.assertFalse(connected)
        self.assertEqual(4004, code)

        # Connect as anonymous user.
        communicator2 = WebsocketCommunicator(
            application, f"{self.private_room_websocket_url}?guest=test"
        )

        connected, code = await communicator2.connect()
        self.assertFalse(connected)
        self.assertEqual(4004, code)

    async def test_join_banned(self):
        """
        Tests that connection is closed with proper error message when user is banned
        from room.
        """
        # Attempting to join public room.
        communicator = WebsocketCommunicator(
            application, self.public_room_websocket_url
        )
        communicator.scope["user"] = self.bad_user

        connected, code = await communicator.connect()
        self.assertFalse(connected)
        self.assertEqual(4005, code)

        # Attempting to join confirmed room.
        communicator2 = WebsocketCommunicator(
            application, self.confirmed_room_websocket_url
        )
        communicator2.scope["user"] = self.bad_user

        connected, code = await communicator2.connect()
        self.assertFalse(connected)
        self.assertEqual(4005, code)

    async def test_join_already_in_room(self):
        """
        Tests that a user cannot join a room that they are already a participant in.
        Also tests that a guest user cannot join a room with the same username as
        another guest participant.
        """
        # Connect as self.allowed_user.
        communicator = WebsocketCommunicator(
            application, self.public_room_websocket_url
        )
        communicator.scope["user"] = self.allowed_user

        connected = (await communicator.connect())[0]
        self.assertTrue(connected)

        response = await communicator.receive_json_from(TIMEOUT)
        self.assertEqual(
            {
                "update": "joined successfully",
                "joined as": self.allowed_user.username,
            },
            response,
        )

        # Attempt to join while original connection is still active.
        communicator2 = WebsocketCommunicator(
            application, self.public_room_websocket_url
        )
        communicator2.scope["user"] = self.allowed_user

        connected, code = await communicator2.connect()
        self.assertFalse(connected)
        self.assertEqual(4006, code)

        # Connect as anonymous user.
        communicator3 = WebsocketCommunicator(
            application, f"{self.public_room_websocket_url}?guest=test"
        )

        connected = (await communicator3.connect())[0]
        self.assertTrue(connected)

        response = await communicator3.receive_json_from(TIMEOUT)
        self.assertEqual(
            {
                "update": "joined successfully",
                "joined as": "guest_test",
            },
            response,
        )

        # Attempt to join while original connection is still active.
        communicator4 = WebsocketCommunicator(
            application, f"{self.public_room_websocket_url}?guest=test"
        )

        connected, code = await communicator4.connect()
        self.assertFalse(connected)
        self.assertEqual(4006, code)

    async def test_rejoin_after_disconnect(self):
        """
        Tests that a user can rejoin a room after disconnecting. Also
        tests that a guest user can rejoin a room after disconnecting,
        assuming no one else joined using the same guest username.
        """
        # Connect as self.allowed_user.
        communicator = WebsocketCommunicator(
            application, self.public_room_websocket_url
        )
        communicator.scope["user"] = self.allowed_user

        connected = (await communicator.connect())[0]
        self.assertTrue(connected)

        response = await communicator.receive_json_from(TIMEOUT)
        self.assertEqual(
            {
                "update": "joined successfully",
                "joined as": self.allowed_user.username,
            },
            response,
        )

        await communicator.disconnect()

        # Rejoin.
        communicator2 = WebsocketCommunicator(
            application, self.public_room_websocket_url
        )
        communicator2.scope["user"] = self.allowed_user

        connected = (await communicator2.connect())[0]
        self.assertTrue(connected)

        response = await communicator2.receive_json_from(TIMEOUT)
        self.assertEqual(
            {
                "update": "joined successfully",
                "joined as": self.allowed_user.username,
            },
            response,
        )

        # Connect as anonymous user.
        communicator3 = WebsocketCommunicator(
            application, f"{self.public_room_websocket_url}?guest=test"
        )

        connected = (await communicator3.connect())[0]
        self.assertTrue(connected)

        response = await communicator3.receive_json_from(TIMEOUT)
        self.assertEqual(
            {
                "update": "joined successfully",
                "joined as": "guest_test",
            },
            response,
        )

        await communicator3.disconnect()

        # Rejoin.
        communicator4 = WebsocketCommunicator(
            application, f"{self.public_room_websocket_url}?guest=test"
        )

        connected = (await communicator4.connect())[0]
        self.assertTrue(connected)

        response = await communicator4.receive_json_from(TIMEOUT)
        self.assertEqual(
            {
                "update": "joined successfully",
                "joined as": "guest_test",
            },
            response,
        )


class ChatroomActionTests(TransactionTestCase):
    """
    Performs tests related to requesting actions from server.
    """

    def setUp(self):
        """
        Sets up environment for tests. Creates two users (one room owner and one normal
        user). A public room is also created.
        """
        self.owner = User.objects.create_user("owner", "owner@example.com", "12345")

        self.user = User.objects.create_user("user", "user@example.com", "12345")

        self.room = Room.objects.create(
            name="Room", number="1234567890", owner=self.owner
        )
        self.room_websocket_url = f"/ws/chat/{self.room.number}/"

    async def test_get_participants(self):
        """
        Tests getting room participants.
        """
        # Connect owner as room participant.
        owner_communicator = WebsocketCommunicator(application, self.room_websocket_url)
        owner_communicator.scope["user"] = self.owner
        await owner_communicator.connect()

        # Connect normal user as room participant.
        user_communicator = WebsocketCommunicator(application, self.room_websocket_url)
        user_communicator.scope["user"] = self.user
        await user_communicator.connect()
        await user_communicator.receive_json_from(TIMEOUT)

        await user_communicator.send_json_to({"action": "get participants"})
        participants = await user_communicator.receive_json_from(TIMEOUT)
        self.assertListEqual(["owner", "user"], participants)

    async def test_send_new_messages(self):
        """
        Tests that all room participants will receive a chat message sent by one
        participant.
        """
        expected_response = {
            "update": "new message",
            "message": "Test message.",
            "username": self.user.username,
        }

        # Connect owner as room participant.
        owner_communicator = WebsocketCommunicator(application, self.room_websocket_url)
        owner_communicator.scope["user"] = self.owner
        await owner_communicator.connect()
        await owner_communicator.receive_json_from(TIMEOUT)

        # Connect normal user as room participant.
        user_communicator = WebsocketCommunicator(application, self.room_websocket_url)
        user_communicator.scope["user"] = self.user
        await user_communicator.connect()
        await user_communicator.receive_json_from(TIMEOUT)

        # Normal user sends message.
        await user_communicator.send_json_to(
            {"action": "send message", "message": "Test message."}
        )
        # Normal user receives update concerning new message.
        response = await user_communicator.receive_json_from(TIMEOUT)
        self.assertEqual(expected_response, response)

        # Owner receives update concerning new message.
        response = await owner_communicator.receive_json_from(TIMEOUT)
        self.assertEqual(expected_response, response)

    async def test_kick_user(self):
        """
        Tests that a room participant can be kicked by room owner.
        """
        # Connect owner as room participant.
        owner_communicator = WebsocketCommunicator(application, self.room_websocket_url)
        owner_communicator.scope["user"] = self.owner
        await owner_communicator.connect()
        await owner_communicator.receive_json_from(TIMEOUT)

        # Connect normal user as room participant.
        user_communicator = WebsocketCommunicator(application, self.room_websocket_url)
        user_communicator.scope["user"] = self.user
        await user_communicator.connect()
        await user_communicator.receive_json_from(TIMEOUT)

        # Owner requests that normal user is kicked.
        await owner_communicator.send_json_to(
            {"action": "kick user", "username": self.user.username}
        )

        # Normal user is kicked.
        response = await user_communicator.receive_json_from(TIMEOUT)
        self.assertEqual({"update": "kicked you"}, response)

        # Owner is alerted that normal user has been kicked.
        response = await owner_communicator.receive_json_from(TIMEOUT)
        self.assertEqual(
            {"update": "user kicked", "username": self.user.username}, response
        )

        # Normal user rejoins.
        user_communicator2 = WebsocketCommunicator(application, self.room_websocket_url)
        user_communicator2.scope["user"] = self.user
        await user_communicator2.connect()
        response = await user_communicator2.receive_json_from(TIMEOUT)
        self.assertEqual(
            {
                "update": "joined successfully",
                "joined as": self.user.username,
            },
            response,
        )

        # Connect anonymous user as room participant.
        guest_communicator = WebsocketCommunicator(
            application, f"{self.room_websocket_url}?guest=test"
        )
        await guest_communicator.connect()
        await guest_communicator.receive_json_from(TIMEOUT)

        # Owner requests that anonymous user is kicked.
        await owner_communicator.send_json_to(
            {"action": "kick user", "username": "guest_test"}
        )

        # Anonymous user is kicked.
        response = await guest_communicator.receive_json_from(TIMEOUT)
        self.assertEqual({"update": "kicked you"}, response)

        # Owner is alerted that anonymous user has been kicked.
        response = await owner_communicator.receive_json_from(TIMEOUT)
        self.assertEqual({"update": "user kicked", "username": "guest_test"}, response)

        # Anonymous user rejoins.
        guest_communicator2 = WebsocketCommunicator(
            application, f"{self.room_websocket_url}?guest=test"
        )
        await guest_communicator2.connect()
        response = await guest_communicator2.receive_json_from(TIMEOUT)
        self.assertEqual(
            {
                "update": "joined successfully",
                "joined as": "guest_test",
            },
            response,
        )

    async def test_ban_user(self):
        """
        Tests that a room participant can be banned by room owner. Also tests that this
        does not apply to guest users.
        """
        # Connect owner as room participant.
        owner_communicator = WebsocketCommunicator(application, self.room_websocket_url)
        owner_communicator.scope["user"] = self.owner
        await owner_communicator.connect()
        await owner_communicator.receive_json_from(TIMEOUT)

        # Connect normal user as room participant.
        user_communicator = WebsocketCommunicator(application, self.room_websocket_url)
        user_communicator.scope["user"] = self.user
        await user_communicator.connect()
        await user_communicator.receive_json_from(TIMEOUT)

        # Owner requests that normal user is banned.
        await owner_communicator.send_json_to(
            {"action": "ban user", "username": self.user.username}
        )

        # Normal user is banned.
        response = await user_communicator.receive_json_from(TIMEOUT)
        self.assertEqual({"update": "banned you"}, response)

        # Owner is alerted that normal user has been banned.
        response = await owner_communicator.receive_json_from(TIMEOUT)
        self.assertEqual(
            {"update": "user banned", "username": self.user.username}, response
        )

        # Normal user cannot rejoin.
        user_communicator2 = WebsocketCommunicator(application, self.room_websocket_url)
        user_communicator2.scope["user"] = self.user
        connected, code = await user_communicator2.connect()
        self.assertFalse(connected)
        self.assertEqual(4005, code)

        # Connect anonymous user as room participant.
        guest_communicator = WebsocketCommunicator(
            application, f"{self.room_websocket_url}?guest=test"
        )
        await guest_communicator.connect()
        await guest_communicator.receive_json_from(TIMEOUT)

        # Owner requests that anonymous user is banned. Request will be ignored.
        await owner_communicator.send_json_to(
            {"action": "ban user", "username": "guest_test"}
        )

        # Anonymous user is still connected.
        await guest_communicator.send_json_to({"action": "get participants"})
        response = await guest_communicator.receive_json_from(TIMEOUT)
        self.assertListEqual(["guest_test", "owner"], response)
