from datetime import datetime

from django.db import models
from django.core.exceptions import ValidationError
from django.conf import settings
from django.utils.functional import cached_property

from drip.utils import get_user_model
from drip.querysets import DripQueryset

# just using this to parse, but totally insane package naming...
# https://bitbucket.org/schinckel/django-timedelta-field/
import timedelta as djangotimedelta


class DripSplitSubject(models.Model):
    drip = models.ForeignKey('Drip', related_name='split_test_subjects')
    subject = models.CharField(max_length=150)
    enabled = models.BooleanField(default=True)


class DripEmailTag(models.Model):
    drip = models.ForeignKey('Drip', related_name='tags')
    tag = models.CharField(
        max_length=128,
        help_text='Tags are case insensitive and should be ascii only. Maximum tag length is 128 characters.')

    def clean(self):
        if self.tag.lower() != self.tag:
            raise ValidationError('Tags are case insensitive. Please, specify lower case tag explicitly.')
        try:
            self.tag.encode('ascii')
        except UnicodeEncodeError:
            raise ValidationError('Tags should be ascii only.')


class Drip(models.Model):
    TEMPLATE_BASE_CHOICES = (
        ('with_base', 'Insert content of body field into default email base template'),
        ('standalone', 'Use content of body as standalone template'),
    )

    date = models.DateTimeField(auto_now_add=True)
    lastchanged = models.DateTimeField(auto_now=True)

    name = models.CharField(
        max_length=255,
        unique=True,
        verbose_name='Drip Name',
        help_text='A unique name for this drip.')

    enabled = models.BooleanField(default=False)

    from_email = models.EmailField(null=True,
                                   blank=True,
                                   help_text='Set a custom from email.')
    from_email_name = models.CharField(
        max_length=150,
        null=True,
        blank=True,
        help_text="Set a name for a custom from email.")
    subject_template = models.TextField(null=True, blank=True)
    body_html_template = models.TextField(
        null=True,
        blank=True,
        help_text=('''
            <pre>
                <strong>For default drip smpt</strong>: You will have settings and user in the context.
                <strong>For Mailgun API</strong>: You will have user variables, specified in settings.MAILGUN['TEMPLATE_VARIABLES'].
                They should be used as {{{{ user.full_name }}}} for `full_name`
                For now these are: {0}
                This is done to not overload Mailgun API with all available fields for every user
            </pre>
        '''.format(settings.MAILGUN.get('TEMPLATE_VARIABLES', []))))
    template_base = models.CharField(
        verbose_name='How to treat body content?',
        max_length=20,
        choices=TEMPLATE_BASE_CHOICES,
        help_text='''
            <pre>
                If selected option is {1}
                <strong>{0}</strong> will be used
            </pre>
        '''.format(settings.MAILGUN['EMAIL_BASE_HTML_TEMPLATE'], TEMPLATE_BASE_CHOICES[0][1]),
    )
    message_class = models.CharField(
        max_length=120,
        blank=True,
        default='default',
    )

    objects = DripQueryset.as_manager()

    def init_drip(self, klass, **kwargs):
        drip = klass(
            drip_model=self,
            name=self.name,
            from_email=self.from_email if self.from_email else None,
            from_email_name=self.from_email_name if self.from_email_name else None,
            subject_template=self.subject_template if self.subject_template else None,
            body_template=self.body_html_template if self.body_html_template else None,
            **kwargs)
        return drip

    @property
    def drip(self):
        from drip.drips import DripBase
        return self.init_drip(klass=DripBase)

    @property
    def drip_mailgun(self):
        from drip.drips import DripMailgun
        return self.init_drip(
            klass=DripMailgun,
            tags_list=self.get_tags_list(),
            template_base=self.template_base,
            base_template_html_path=settings.MAILGUN.get('EMAIL_BASE_HTML_TEMPLATE'),
            drip_instance=self,
        )

    def get_blog_entries_for_newsletter(self, count=5):
        from photoblog.blog_entries.models import BlogEntry
        return BlogEntry.objects.order_by('-created')[:5]

    def __unicode__(self):
        return self.name

    @cached_property
    def get_split_test_subjects(self):
        return self.split_test_subjects.filter(enabled=True)

    @property
    def split_test_active(self):
        if self.get_split_test_subjects:
            return True
        return False

    def choose_split_test_subject(self):
        random_subject = self.get_split_test_subjects.order_by('?')[0]
        return random_subject.subject

    def get_tags_list(self):
        tags_max_count = settings.MAILGUN.get('MAX_TAGS_COUNT', 3)
        tags = list(self.tags.values_list('tag', flat=True))[:tags_max_count]
        return tags


class SentDrip(models.Model):
    """
    Keeps a record of all sent drips.
    """
    date = models.DateTimeField(auto_now_add=True)

    drip = models.ForeignKey('drip.Drip', related_name='sent_drips')
    user = models.ForeignKey(getattr(settings, 'AUTH_USER_MODEL', 'auth.User'), related_name='sent_drips')

    subject = models.TextField()
    # body = models.TextField()
    from_email = models.EmailField(
        null=True,
        default=None,
    )
    from_email_name = models.CharField(
        max_length=150,
        null=True,
        default=None,
    )


METHOD_TYPES = (
    ('filter', 'Filter'),
    ('exclude', 'Exclude'),
)

LOOKUP_TYPES = (
    ('exact', 'exactly'),
    ('iexact', 'exactly (case insensitive)'),
    ('contains', 'contains'),
    ('icontains', 'contains (case insensitive)'),
    ('regex', 'regex'),
    ('iregex', 'contains (case insensitive)'),
    ('gt', 'greater than'),
    ('gte', 'greater than or equal to'),
    ('lt', 'less than'),
    ('lte', 'less than or equal to'),
    ('startswith', 'starts with'),
    ('endswith', 'starts with'),
    ('istartswith', 'ends with (case insensitive)'),
    ('iendswith', 'ends with (case insensitive)'),
)


class QuerySetRule(models.Model):
    date = models.DateTimeField(auto_now_add=True)
    lastchanged = models.DateTimeField(auto_now=True)

    drip = models.ForeignKey(Drip, related_name='queryset_rules')

    method_type = models.CharField(max_length=12, default='filter', choices=METHOD_TYPES)
    field_name = models.CharField(max_length=128, verbose_name='Field name of User')
    lookup_type = models.CharField(max_length=12, default='exact', choices=LOOKUP_TYPES)

    field_value = models.CharField(
        max_length=255,
        help_text=('Can be anything from a number, to a string. Or, do ' +
                   '`now-7 days` or `today+3 days` for fancy timedelta.'))

    def clean(self):
        User = get_user_model()
        try:
            self.apply(User.objects.all())
        except Exception as e:
            raise ValidationError(
                '%s raised trying to apply rule: %s' % (type(e).__name__, e))

    @property
    def annotated_field_name(self):
        field_name = self.field_name
        if field_name.endswith('__count'):
            agg, _, _ = field_name.rpartition('__')
            field_name = 'num_%s' % agg.replace('__', '_')

        return field_name

    def apply_any_annotation(self, qs):
        if self.field_name.endswith('__count'):
            field_name = self.annotated_field_name
            agg, _, _ = self.field_name.rpartition('__')
            qs = qs.annotate(**{field_name: models.Count(agg, distinct=True)})
        return qs

    def filter_kwargs(self, qs, now=datetime.now):
        # Support Count() as m2m__count
        field_name = self.annotated_field_name
        field_name = '__'.join([field_name, self.lookup_type])
        field_value = self.field_value

        # set time deltas and dates
        if self.field_value.startswith('now-'):
            field_value = self.field_value.replace('now-', '')
            field_value = now() - djangotimedelta.parse(field_value)
        elif self.field_value.startswith('now+'):
            field_value = self.field_value.replace('now+', '')
            field_value = now() + djangotimedelta.parse(field_value)
        elif self.field_value.startswith('today-'):
            field_value = self.field_value.replace('today-', '')
            field_value = now().date() - djangotimedelta.parse(field_value)
        elif self.field_value.startswith('today+'):
            field_value = self.field_value.replace('today+', '')
            field_value = now().date() + djangotimedelta.parse(field_value)

        # F expressions
        if self.field_value.startswith('F_'):
            field_value = self.field_value.replace('F_', '')
            field_value = models.F(field_value)

        # set booleans
        if self.field_value == 'True':
            field_value = True
        if self.field_value == 'False':
            field_value = False

        kwargs = {field_name: field_value}

        return kwargs

    def apply(self, qs, now=datetime.now):

        kwargs = self.filter_kwargs(qs, now)
        qs = self.apply_any_annotation(qs)

        if self.method_type == 'filter':
            return qs.filter(**kwargs)
        elif self.method_type == 'exclude':
            return qs.exclude(**kwargs)

        # catch as default
        return qs.filter(**kwargs)
