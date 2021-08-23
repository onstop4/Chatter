from django.contrib.auth import get_user_model
from django.db.utils import IntegrityError
from django.test import TestCase


class UserCreationTests(TestCase):
    user_model = get_user_model()
    user_manager = user_model.objects

    def test_create_user(self):
        user = self.user_model.objects.create_user("test", "test@example.com", "12345")
        self.assertEqual(user.username, "test")
        self.assertEqual(user.email, "test@example.com")
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_superuser)

        with self.assertRaises(IntegrityError):
            self.user_model.objects.create_user("test", "whatever@example.com", "67890")

    def test_create_superuser(self):
        user = self.user_model.objects.create_superuser(
            "test", "test@example.com", "12345"
        )
        self.assertEqual(user.username, "test")
        self.assertEqual(user.email, "test@example.com")
        self.assertTrue(user.is_active)
        self.assertTrue(user.is_superuser)

        with self.assertRaises(IntegrityError):
            self.user_model.objects.create_user("test", "whatever@example.com", "67890")


class UserLoginTests(TestCase):
    credentials = {
        "username": "test",
        "email": "test@example.com",
        "password": "uQygs8HXqq",
    }

    def test_login(self):
        """
        Tests user login.
        """
        response = self.client.post("/login/", self.credentials, follow=True)
        self.assertEqual(response.status_code, 200)
