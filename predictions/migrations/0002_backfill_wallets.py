from decimal import Decimal
from django.conf import settings
from django.db import migrations

def create_existing_wallets(apps, schema_editor):
    User = apps.get_model(*settings.AUTH_USER_MODEL.split('.'))
    Wallet = apps.get_model('predictions', 'Wallet')
    Transaction = apps.get_model('predictions', 'Transaction')
    db = schema_editor.connection.alias
    for user in User.objects.using(db).all().iterator():
        wallet, created = Wallet.objects.using(db).get_or_create(user_id=user.pk, defaults={'balance': Decimal('1000.00')})
        if created:
            Transaction.objects.using(db).create(wallet_id=wallet.pk, type='grant', amount=wallet.balance, balance_before=Decimal('0'), balance_after=wallet.balance, description='Starting virtual credit grant')

class Migration(migrations.Migration):
    dependencies = [
        ('predictions', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [migrations.RunPython(create_existing_wallets, migrations.RunPython.noop)]
