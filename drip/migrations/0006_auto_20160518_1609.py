# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('blog_entries', '0036_featuredtag'),
        ('drip', '0005_auto_20160513_1610'),
    ]

    operations = [
        migrations.AddField(
            model_name='drip',
            name='blog_entries',
            field=models.ManyToManyField(related_name='drips', to='blog_entries.BlogEntry'),
        ),
        migrations.AlterField(
            model_name='drip',
            name='body_html_template',
            field=models.TextField(help_text=b"\n            <pre>\n                <strong>For default drip smpt</strong>: You will have settings and user in the context.\n                <strong>For Mailgun API</strong>: You will have user variables, specified in settings.MAILGUN['TEMPLATE_VARIABLES'].\n                They should be used as {{ user.full_name }} for `full_name`\n                For now these are: (u'full_name', u'id', u'avatar_url')\n                This is done to not overload Mailgun API with all available fields for every user\n            </pre>\n        ", null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='drip',
            name='template_base',
            field=models.CharField(help_text=b'\n            <pre>\n                If selected option is Insert content of body field into default email base template\n                <strong>common/email/newsletter_base.html</strong> will be used\n            </pre>\n        ', max_length=20, verbose_name=b'How to treat body content?', choices=[(b'with_base', b'Insert content of body field into default email base template'), (b'standalone', b'Use content of body as standalone template')]),
        ),
    ]
