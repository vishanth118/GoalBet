
    def __init__(self, *args, grand_prix=None, **kwargs):
        super().__init__(*args, **kwargs)

        sessions = Session.objects.filter(
            status=Session.Status.SCHEDULED
        )
        if grand_prix is not None:
            sessions = sessions.filter(grand_prix=grand_prix)

        self.fields['session'].queryset = sessions

        drivers = Driver.objects.filter(
            active=True
        ).select_related('constructor')
        if grand_prix is not None:
            drivers = drivers.filter(grand_prix_entries=grand_prix)

        self.fields['driver'].queryset = drivers

        # Find the session selected for this form.
        session_id = (
            self.data.get(self.add_prefix('session'))
            if self.is_bound
            else self.initial.get('session')
        )

        session = (
            sessions.filter(pk=session_id).first()
            if session_id
            else None
        )

        # Show only markets supported by the selected session.
        if session is not None:
            self.fields['market'].choices = [
                (value, label)
                for value, label in F1Prediction.Market.choices
                if MARKET_SESSION_TYPES.get(value) == session.session_type
            ]
        else:
            self.fields['market'].choices = []

