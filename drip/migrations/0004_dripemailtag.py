# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('drip', '0003_auto_20150814_0724'),
    ]

    operations = [
        migrations.CreateModel(
            name='DripEmailTag',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('tag', models.CharField(help_text=b'Tags are case insensitive and should be ascii only. Maximum tag length is 128 characters.', max_length=128)),
                ('drip', models.ForeignKey(related_name='tags', to='drip.Drip')),
            ],
        ),
    ]
