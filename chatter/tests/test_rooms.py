from django.contrib.auth.models import AnonymousUser
from django.test import TestCase

from chatter.models import Room, RoomAccessStatus, User


class RoomCreationTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("owner", "owner@example.com", "12345")

    def test_create_room(self):
        """
        Tests that Room instances can be created successfully.
        """
        room = Room.objects.create(name="Room", owner=self.owner)
        self.assertEqual(len(room.number), 10)
        self.assertEqual(room.access_type, "PUBLIC")


class RoomAccessTests(TestCase):
    """
    Tests the RoomManager.get_access_status method.
    """

    def setUp(self):
        self.owner = User.objects.create_user("owner", "owner@example.com", "12345")
        self.room = Room.objects.create(
            name="Room", number="1234567890", owner=self.owner
        )
        self.other_user = User.objects.create_user("test", "test@example.com", "12345")

    def test_good_public(self):
        """
        Tests that public rooms can be accessed by users regardless of whether or not
        they are logged in.
        """
        self.assertEqual(
            (self.room, RoomAccessStatus.ALLOWED),
            Room.objects.get_access_status(
                self.room.number, AnonymousUser(), "guest_other"
            ),
        )
        self.assertEqual(
            (self.room, RoomAccessStatus.ALLOWED),
            Room.objects.get_access_status(self.room.number, self.other_user, "test"),
        )

    def test_good_confirmed(self):
        """
        Tests that confirmed-only rooms can be accessed by logged in users.
        """
        self.room.access_type = Room.AccessTypes.CONFIRMED
        self.room.save()

        self.assertEqual(
            (self.room, RoomAccessStatus.ALLOWED),
            Room.objects.get_access_status(
                self.room.number, self.other_user, self.other_user.username
            ),
        )

    def test_good_private(self):
        """
        Tests that private rooms can be accessed by invited users.
        """
        self.room.access_type = Room.AccessTypes.PRIVATE
        self.room.invited_users.add(self.other_user)
        self.room.save()

        self.assertEqual(
            (self.room, RoomAccessStatus.ALLOWED),
            Room.objects.get_access_status(
                self.room.number, self.other_user, self.other_user.username
            ),
        )

    def test_not_found(self):
        """
        Tests that NOT_FOUND will be returned for unknown rooms.
        """
        self.assertEqual(
            (None, RoomAccessStatus.NOT_FOUND),
            Room.objects.get_access_status("0987654321", AnonymousUser(), "guest_test"),
        )

    def test_bad_username(self):
        """
        Tests that BAD_USERNAME will be returned for bad usernames. Also tests that
        users who are logged in won't receive BAD_USERNAME regardless of username.
        """
        self.assertEqual(
            (self.room, RoomAccessStatus.BAD_USERNAME),
            Room.objects.get_access_status(self.room.number, AnonymousUser(), ""),
        )
        self.assertEqual(
            (self.room, RoomAccessStatus.BAD_USERNAME),
            Room.objects.get_access_status(self.room.number, AnonymousUser(), " "),
        )

        # When logged in, get_access_status won't return BAD_USERNAME.
        self.assertEqual(
            (self.room, RoomAccessStatus.ALLOWED),
            Room.objects.get_access_status(self.room.number, self.other_user, ""),
        )
        self.assertEqual(
            (self.room, RoomAccessStatus.ALLOWED),
            Room.objects.get_access_status(self.room.number, self.other_user, " "),
        )

    def test_confirm_required(self):
        """
        Tests that users who are not logged in will receive CONFIRM_REQUIRED for
        confirmed-only rooms.
        """
        self.room.access_type = Room.AccessTypes.CONFIRMED
        self.room.save()

        self.assertEqual(
            (self.room, RoomAccessStatus.CONFIRM_REQUIRED),
            Room.objects.get_access_status(
                self.room.number, AnonymousUser(), "guest_test"
            ),
        )

    def test_not_invited(self):
        """
        Tests that users who are not invited to private rooms will receive NOT_INVITED.
        """
        self.room.access_type = Room.AccessTypes.PRIVATE
        self.room.save()

        self.assertEqual(
            (self.room, RoomAccessStatus.NOT_INVITED),
            Room.objects.get_access_status(
                self.room.number, AnonymousUser(), "guest_test"
            ),
        )
        self.assertEqual(
            (self.room, RoomAccessStatus.NOT_INVITED),
            Room.objects.get_access_status(self.room.number, self.other_user, "test"),
        )

    def test_banned(self):
        """
        Tests that users banned from confirmed-only will receive BANNED.
        """
        self.room.access_type = Room.AccessTypes.CONFIRMED
        self.room.banned_users.add(self.other_user)
        self.room.save()

        self.assertEqual(
            (self.room, RoomAccessStatus.BANNED),
            Room.objects.get_access_status(self.room.number, self.other_user, "test"),
        )
