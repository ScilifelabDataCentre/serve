from typing import Optional, Sequence
import re

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.core.validators import EmailValidator
from django.utils.safestring import mark_safe
from django.core.exceptions import ValidationError


EMAIL_ALLOW_REGEX = re.compile(
        (r"^(?:.*\.)?("
         "uu"            # Uppsala universitets webbplats"
         "|lu"           # Lunds universitets webbplats"
         "|gu"           # Göteborgs universitets webbplats"
         "|su"           # Stockholms universitets webbplats"
         "|umu"          # Umeå universitets webbplats"
         "|liu"          # Linköpings universitets webbplats"
         "|ki"           # Karolinska institutets webbplats"
         "|kth"          # Kungliga Tekniska högskolans webbplats"
         "|chalmers"     # Chalmers tekniska högskolas webbplats"
         "|ltu"          # Luleå tekniska universitets webbplats"
         "|hhs"          # Handelshögskolan i Stockholms webbplats"
         "|slu"          # Sveriges lantbruksuniversitets webbplats"
         "|kau"          # Karlstads universitets webbplats"
         "|lnu"          # Linnéuniversitetets webbplats"
         "|oru"          # Örebro universitets webbplats"
         "|miun"         # Mittuniversitetets webbplats"
         "|mau"          # Malmö universitets webbplats"
         "|mdu"          # Mälardalens universitets webbplats"
         "|bth"          # Blekinge tekniska högskolas webbplats"
         "|fhs"          # Försvarshögskolans webbplats"
         "|gih"          # Gymnastik- och idrottshögskolans webbplats"
         "|hb"           # Högskolan i Borås webbplats"
         "|du"           # Högskolan Dalarnas webbplats"
         "|hig"          # Högskolan i Gävles webbplats"
         "|hh"           # Högskolan i Halmstads webbplats"
         "|hkr"          # Högskolan Kristianstads webbplats"
         "|his"          # Högskolan i Skövdes webbplats"
         "|hv"           # Högskolan Västs webbplats"
         "|ju"           # Stiftelsen Högskolan i Jönköpings webbplats"
         "|sh"           # Södertörns högskolas webbplats"
         "|nbis"         # National Bioinformatics Infrastructure Sweden
         "|scilifelab"   # Science for Life Laboratory
         ")\.se$"
        )
)


# Sign Up Form
class SignUpForm(UserCreationForm):

    first_name = forms.CharField(
        max_length=30,
        required=False,
        label=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "First name"}),
    )
    last_name = forms.CharField(
        max_length=30,
        required=False,
        label=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Last name"}),
    )
    email = forms.EmailField(
        max_length=254,
        label=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Email*"}),
        validators=(EmailValidator(allowlist=["uu.se"]),),
    )
    password1 = forms.CharField(
        label=False,
        widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "Password*"}),
    )
    password2 = forms.CharField(
        label=False,
        widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "Confirm"}),
    )

    class Meta:
        model = User
        fields = [
            "username",
            "first_name",
            "last_name",
            "email",
            "password1",
            "password2",
        ]

    def clean_email(self) -> str:
        email = self.cleaned_data["email"]
        if EMAIL_ALLOW_REGEX.match(email) is None:
            raise ValidationError(
                    mark_safe(
                        "Please use your <a "
                        "href='https://www.uka.se/sa-fungerar-hogskolan/universitet-och-hogskolor/lista-over-"
                        "universitet-hogskolor-och-enskilda-utbildningsanordnare'>"
                        "swedish university</a> email address."
                        )
                    )
