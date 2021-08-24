from django.test import TestCase

from chatter.models import Room, User


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
