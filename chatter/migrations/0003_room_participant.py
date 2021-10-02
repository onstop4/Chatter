# Generated by Django 3.2.6 on 2021-10-02 14:19

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("chatter", "0002_room"),
    ]

    operations = [
        migrations.CreateModel(
            name="RoomParticipant",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("username", models.CharField(max_length=30, verbose_name="Username")),
                (
                    "room",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="participants",
                        to="chatter.room",
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="roomparticipant",
            constraint=models.UniqueConstraint(
                fields=("room", "username"), name="room_username"
            ),
        ),
    ]
