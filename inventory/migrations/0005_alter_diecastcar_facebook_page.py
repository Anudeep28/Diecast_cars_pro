# Generated by Django 5.2.4 on 2025-07-06 16:28

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0004_diecastcar_facebook_page'),
    ]

    operations = [
        migrations.AlterField(
            model_name='diecastcar',
            name='facebook_page',
            field=models.CharField(blank=True, max_length=500, null=True),
        ),
    ]
