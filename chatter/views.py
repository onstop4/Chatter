from django.contrib.auth import login
from django.views.generic import CreateView, TemplateView

from chatter.forms import RegisterForm


class IndexView(TemplateView):
    def get_context_data(self, **kwargs):
        if self.request.GET.get("new_user"):
            kwargs["new_user"] = True
        return kwargs


class RegisterView(CreateView):
    form_class = RegisterForm
    template_name = "chatter/register.html"
    success_url = "/?new_user=1"

    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object)
        return response
