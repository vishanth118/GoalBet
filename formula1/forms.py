
from decimal import Decimal

from django import forms

from .models import Driver, Session
from predictions.models import F1Prediction


MARKETS_BY_SESSION_TYPE = {
    Session.Type.QUALIFYING: [
        F1Prediction.Market.POLE,
    ],
    Session.Type.SPRINT_QUALIFYING: [
        F1Prediction.Market.POLE,
    ],
    Session.Type.GRAND_PRIX: [
        F1Prediction.Market.RACE_WINNER,
        F1Prediction.Market.PODIUM,
        F1Prediction.Market.FASTEST_LAP,
    ],
}


class F1PredictionForm(forms.Form):
    session = forms.ModelChoiceField(
        queryset=Session.objects.none(),
        widget=forms.HiddenInput,
    )

    market = forms.ChoiceField(
        choices=[],
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    driver = forms.ModelChoiceField(
        queryset=Driver.objects.none(),
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    stake = forms.DecimalField(
        min_value=Decimal("1"),
        max_digits=10,
        decimal_places=2,
        widget=forms.NumberInput(
            attrs={
                "min": "1",
                "step": "1",
                "class": "form-control",
            }
        ),
    )

    def __init__(self, *args, grand_prix=None, **kwargs):
        super().__init__(*args, **kwargs)

        sessions = Session.objects.filter(
            status=Session.Status.SCHEDULED,
        )

        if grand_prix is not None:
            sessions = sessions.filter(grand_prix=grand_prix)

        self.fields["session"].queryset = sessions

        drivers = Driver.objects.filter(
            active=True,
        ).select_related("constructor")

        if grand_prix is not None:
            drivers = drivers.filter(grand_prix_entries=grand_prix)

        self.fields["driver"].queryset = drivers

        session_id = self.data.get(self.add_prefix("session"))

        if not session_id:
            session_id = self.initial.get("session")

        session = None

        if isinstance(session_id, Session):
            session = session_id
        elif session_id:
            try:
                session = sessions.filter(pk=session_id).first()
            except (ValueError, TypeError):
                session = None

        supported_markets = []

        if session:
            supported_markets = MARKETS_BY_SESSION_TYPE.get(
                session.session_type,
                [],
            )

        self.fields["market"].choices = [
            (value, label)
            for value, label in F1Prediction.Market.choices
            if value in supported_markets
        ]

    def clean(self):
        cleaned = super().clean()

        session = cleaned.get("session")
        market = cleaned.get("market")

        if session and market:
            supported_markets = MARKETS_BY_SESSION_TYPE.get(
                session.session_type,
                [],
            )

            if market not in supported_markets:
                self.add_error(
                    "market",
                    "Choose a market supported by this session type.",
                )

        return cleaned
