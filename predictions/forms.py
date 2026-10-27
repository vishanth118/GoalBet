from decimal import Decimal
from django import forms
from django.contrib.auth import get_user_model, password_validation
from django.core.exceptions import ValidationError
from .models import Prediction

class PredictionForm(forms.Form):
    market = forms.ChoiceField(choices=Prediction.Market.choices, widget=forms.Select(attrs={'class': 'form-select'}))
    outcome = forms.ChoiceField(choices=(), widget=forms.Select(attrs={'class': 'form-select'}))
    stake = forms.DecimalField(min_value=Decimal('1'), max_digits=10, decimal_places=2, widget=forms.NumberInput(attrs={'min':'1','step':'1','class':'form-control'}))

    MARKET_OUTCOMES = {
        Prediction.Market.MATCH_RESULT: (Prediction.Outcome.HOME, Prediction.Outcome.DRAW, Prediction.Outcome.AWAY),
        Prediction.Market.BOTH_TEAMS_SCORE: (Prediction.Outcome.YES, Prediction.Outcome.NO),
        Prediction.Market.TOTAL_GOALS: (Prediction.Outcome.OVER_25, Prediction.Outcome.UNDER_25),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        market = self.data.get(self.add_prefix('market'), self.initial.get('market', Prediction.Market.MATCH_RESULT))
        if market not in self.MARKET_OUTCOMES:
            market = Prediction.Market.MATCH_RESULT
        self.fields['outcome'].choices = [
            (value, Prediction.Outcome(value).label) for value in self.MARKET_OUTCOMES[market]
        ]

class RegistrationForm(forms.Form):
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={'class': 'form-control', 'autocomplete': 'username'}),
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={'class': 'form-control', 'autocomplete': 'email'}),
    )
    password = forms.CharField(
        min_length=8,
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'autocomplete': 'new-password'}),
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'autocomplete': 'new-password'}),
    )

    def clean_username(self):
        username = self.cleaned_data['username']
        user_model = get_user_model()
        if user_model._default_manager.filter(username=username).exists():
            raise ValidationError('That username is unavailable. Please choose another.')
        return username

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirmation = cleaned_data.get('confirm_password')
        if password and confirmation and password != confirmation:
            self.add_error('confirm_password', 'Passwords do not match.')
            return cleaned_data

        username = cleaned_data.get('username')
        email = cleaned_data.get('email')
        if password and username and email:
            user = get_user_model()(username=username, email=email)
            try:
                password_validation.validate_password(password, user=user)
            except ValidationError as error:
                self.add_error('password', error)
        return cleaned_data
