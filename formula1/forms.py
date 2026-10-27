from decimal import Decimal
from django import forms
from .models import Driver, Session
from predictions.models import F1Prediction

MARKET_SESSION_TYPES = {
    F1Prediction.Market.RACE_WINNER: Session.Type.GRAND_PRIX,
    F1Prediction.Market.PODIUM: Session.Type.GRAND_PRIX,
    F1Prediction.Market.FASTEST_LAP: Session.Type.GRAND_PRIX,
    F1Prediction.Market.POLE: Session.Type.QUALIFYING,
}

class F1PredictionForm(forms.Form):
    session = forms.ModelChoiceField(queryset=Session.objects.none(), widget=forms.HiddenInput)
    market = forms.ChoiceField(choices=F1Prediction.Market.choices, widget=forms.Select(attrs={'class': 'form-select'}))
    driver = forms.ModelChoiceField(queryset=Driver.objects.none(), widget=forms.Select(attrs={'class': 'form-select'}))
    stake = forms.DecimalField(min_value=Decimal('1'), max_digits=10, decimal_places=2, widget=forms.NumberInput(attrs={'min': '1', 'step': '1', 'class': 'form-control'}))

    def __init__(self, *args, grand_prix=None, **kwargs):
        super().__init__(*args, **kwargs)
        sessions = Session.objects.filter(status=Session.Status.SCHEDULED)
        if grand_prix is not None:
            sessions = sessions.filter(grand_prix=grand_prix)
        self.fields['session'].queryset = sessions
        drivers = Driver.objects.filter(active=True).select_related('constructor')
        if grand_prix is not None:
            drivers = drivers.filter(grand_prix_entries=grand_prix)
        self.fields['driver'].queryset = drivers

    def clean(self):
        cleaned = super().clean()
        session = cleaned.get('session')
        market = cleaned.get('market')
        if session and market in MARKET_SESSION_TYPES and session.session_type != MARKET_SESSION_TYPES[market]:
            self.add_error('market', 'Choose a market supported by this session type.')
        return cleaned
