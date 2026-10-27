from django.apps import AppConfig

class PredictionsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'predictions'
    def ready(self):
        from django.contrib.auth import get_user_model
        from django.db.models.signals import post_save
        from .models import Wallet
        post_save.connect(self.create_wallet, sender=get_user_model(), dispatch_uid='create_virtual_wallet')
    @staticmethod
    def create_wallet(sender, instance, created, **kwargs):
        if created:
            from django.conf import settings
            from .models import Transaction, Wallet
            wallet, wallet_created = Wallet.objects.get_or_create(user=instance, defaults={'balance': settings.INITIAL_VIRTUAL_CREDITS})
            if wallet_created:
                Transaction.objects.create(wallet=wallet, type=Transaction.Type.GRANT, amount=wallet.balance, balance_before=0, balance_after=wallet.balance, description='Starting virtual credit grant')
