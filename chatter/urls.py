from django.contrib.auth import views as auth_views
from django.urls import path

from chatter.views import IndexView, RegisterView

urlpatterns = [
    path("", IndexView.as_view(template_name="chatter/index.html"), name="index"),
    path(
        "login/",
        auth_views.LoginView.as_view(
            template_name="chatter/login.html", redirect_authenticated_user=True
        ),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(next_page="login"), name="logout"),
    path("register/", RegisterView.as_view(), name="register"),
]
