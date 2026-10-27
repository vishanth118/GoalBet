from django import forms


class SupportTicketForm(forms.Form):
    email = forms.EmailField(max_length=254, required=False, widget=forms.EmailInput(attrs={'autocomplete': 'email'}))
    subject = forms.CharField(max_length=160, widget=forms.TextInput(attrs={'maxlength': 160}))
    question = forms.CharField(min_length=8, max_length=5000, widget=forms.Textarea(attrs={'rows': 5, 'maxlength': 5000}))
    description = forms.CharField(max_length=10000, required=False, widget=forms.Textarea(attrs={'rows': 4, 'maxlength': 10000}))

    def __init__(self, *args, require_email=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].required = require_email
