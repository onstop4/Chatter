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


class ChatConsumerTests(TransactionTestCase):
    """
    Performs tests related to ChatConsumer.
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
                "update": "join status",
                "status": "allowed",
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
            {"update": "join status", "status": "allowed", "joined as": "guest_test"},
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
                "update": "join status",
                "status": "allowed",
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
                "update": "join status",
                "status": "allowed",
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

        connected = (await communicator.connect())[0]
        self.assertTrue(connected)

        response = await communicator.receive_json_from(TIMEOUT)
        self.assertEqual({"update": "join status", "status": "not found"}, response)

        connected = (await communicator.connect())[0]
        self.assertFalse(connected)

        # Connect as anonymous user.
        communicator2 = WebsocketCommunicator(application, "/ws/chat/54321/")

        connected = (await communicator2.connect())[0]
        self.assertTrue(connected)

        response = await communicator2.receive_json_from(TIMEOUT)
        self.assertEqual({"update": "join status", "status": "not found"}, response)

        connected = (await communicator2.connect())[0]
        self.assertFalse(connected)

    async def test_join_bad_username(self):
        """
        Tests that connection is closed with proper error message when guest user has a
        bad username.
        """
        # Username specified is space character.
        communicator = WebsocketCommunicator(
            application, f"{self.public_room_websocket_url}?guest=%20"
        )

        connected = (await communicator.connect())[0]
        self.assertTrue(connected)

        response = await communicator.receive_json_from(TIMEOUT)
        self.assertEqual({"update": "join status", "status": "bad username"}, response)

        connected = (await communicator.connect())[0]
        self.assertFalse(connected)

        # Username specified is blank.
        communicator2 = WebsocketCommunicator(
            application, f"{self.public_room_websocket_url}?guest="
        )

        connected = (await communicator2.connect())[0]
        self.assertTrue(connected)

        response = await communicator2.receive_json_from(TIMEOUT)
        self.assertEqual({"update": "join status", "status": "bad username"}, response)

        connected = (await communicator2.connect())[0]
        self.assertFalse(connected)

        # Username specified includes space character.
        communicator3 = WebsocketCommunicator(
            application, f"{self.public_room_websocket_url}?guest=test%20bad"
        )

        connected = (await communicator3.connect())[0]
        self.assertTrue(connected)

        response = await communicator3.receive_json_from(TIMEOUT)
        self.assertEqual({"update": "join status", "status": "bad username"}, response)

        connected = (await communicator3.connect())[0]
        self.assertFalse(connected)

        # No username is specified.
        communicator4 = WebsocketCommunicator(
            application, self.public_room_websocket_url
        )

        connected = (await communicator4.connect())[0]
        self.assertTrue(connected)

        response = await communicator4.receive_json_from(TIMEOUT)
        self.assertEqual({"update": "join status", "status": "bad username"}, response)

        connected = (await communicator4.connect())[0]
        self.assertFalse(connected)

    async def test_join_confirm_required(self):
        """
        Tests that connection is closed with proper error message when a guest user
        tries to join a confirmed room.
        """
        communicator = WebsocketCommunicator(
            application, f"{self.confirmed_room_websocket_url}?guest=test"
        )

        connected = (await communicator.connect())[0]
        self.assertTrue(connected)

        response = await communicator.receive_json_from(TIMEOUT)
        self.assertEqual(
            {"update": "join status", "status": "confirm required"}, response
        )

        connected = (await communicator.connect())[0]
        self.assertFalse(connected)

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

        connected = (await communicator.connect())[0]
        self.assertTrue(connected)

        response = await communicator.receive_json_from(TIMEOUT)
        self.assertEqual({"update": "join status", "status": "not invited"}, response)

        connected = (await communicator.connect())[0]
        self.assertFalse(connected)

        # Connect as anonymous user.
        communicator2 = WebsocketCommunicator(
            application, f"{self.private_room_websocket_url}?guest=test"
        )

        connected = (await communicator2.connect())[0]
        self.assertTrue(connected)

        response = await communicator2.receive_json_from(TIMEOUT)
        self.assertEqual({"update": "join status", "status": "not invited"}, response)

        connected = (await communicator2.connect())[0]
        self.assertFalse(connected)

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

        connected = (await communicator.connect())[0]
        self.assertTrue(connected)

        response = await communicator.receive_json_from(TIMEOUT)
        self.assertEqual({"update": "join status", "status": "banned"}, response)

        connected = (await communicator.connect())[0]
        self.assertFalse(connected)

        # Attempting to join confirmed room.
        communicator2 = WebsocketCommunicator(
            application, self.confirmed_room_websocket_url
        )
        communicator2.scope["user"] = self.bad_user

        connected = (await communicator2.connect())[0]
        self.assertTrue(connected)

        response = await communicator2.receive_json_from(TIMEOUT)
        self.assertEqual({"update": "join status", "status": "banned"}, response)

        connected = (await communicator2.connect())[0]
        self.assertFalse(connected)

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
                "update": "join status",
                "status": "allowed",
                "joined as": self.allowed_user.username,
            },
            response,
        )

        # Attempt to join while original connection is still active.
        communicator2 = WebsocketCommunicator(
            application, self.public_room_websocket_url
        )
        communicator2.scope["user"] = self.allowed_user

        connected = (await communicator2.connect())[0]
        self.assertTrue(connected)

        response = await communicator2.receive_json_from(TIMEOUT)
        self.assertEqual(
            {"update": "join status", "status": "already in room"},
            response,
        )

        connected = (await communicator2.connect())[0]
        self.assertFalse(connected)

        # Ensure that original connection is still active.
        connected = (await communicator.connect())[0]
        self.assertTrue(connected)

        # Connect as anonymous user.
        communicator3 = WebsocketCommunicator(
            application, f"{self.public_room_websocket_url}?guest=test"
        )

        connected = (await communicator3.connect())[0]
        self.assertTrue(connected)

        response = await communicator3.receive_json_from(TIMEOUT)
        self.assertEqual(
            {
                "update": "join status",
                "status": "allowed",
                "joined as": "guest_test",
            },
            response,
        )

        # Attempt to join while original connection is still active.
        communicator4 = WebsocketCommunicator(
            application, f"{self.public_room_websocket_url}?guest=test"
        )

        connected = (await communicator4.connect())[0]
        self.assertTrue(connected)

        response = await communicator4.receive_json_from(TIMEOUT)
        self.assertEqual(
            {"update": "join status", "status": "already in room"},
            response,
        )

        connected = (await communicator4.connect())[0]
        self.assertFalse(connected)

        # Ensure that original connection is still active.
        connected = (await communicator3.connect())[0]
        self.assertTrue(connected)

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
                "update": "join status",
                "status": "allowed",
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
                "update": "join status",
                "status": "allowed",
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
                "update": "join status",
                "status": "allowed",
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
                "update": "join status",
                "status": "allowed",
                "joined as": "guest_test",
            },
            response,
        )
