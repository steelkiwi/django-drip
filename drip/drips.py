import operator
import functools

from django.conf import settings
from django.db.models import Q
from django.template import Context, Template
from django.utils.importlib import import_module
from django.core.mail import EmailMultiAlternatives
from django.utils.html import strip_tags

from drip.models import SentDrip
from drip.utils import get_user_model
from drip import mailgun

try:
    from django.utils.timezone import now as conditional_now
except ImportError:
    from datetime import datetime
    conditional_now = datetime.now


import logging


def configured_message_classes():
    conf_dict = getattr(settings, 'DRIP_MESSAGE_CLASSES', {})
    if 'default' not in conf_dict:
        conf_dict['default'] = 'drip.drips.DripMessage'
    return conf_dict


def message_class_for(name):
    path = configured_message_classes()[name]
    mod_name, klass_name = path.rsplit('.', 1)
    mod = import_module(mod_name)
    klass = getattr(mod, klass_name)
    return klass


class DripMessage(object):

    def __init__(self, drip_base, user):
        self.drip_base = drip_base
        self.user = user
        self._context = None
        self._subject = None
        self._body = None
        self._plain = None
        self._message = None

    @property
    def from_email(self):
        return self.drip_base.from_email

    @property
    def from_email_name(self):
        return self.drip_base.from_email_name

    @property
    def context(self):
        if not self._context:
            self._context = Context({'user': self.user})
        return self._context

    @property
    def subject(self):
        if not self._subject:
            self._subject = Template(self.drip_base.subject_template).render(self.context)
        return self._subject

    @property
    def body(self):
        if not self._body:
            self._body = Template(self.drip_base.body_template).render(self.context)
        return self._body

    @property
    def plain(self):
        if not self._plain:
            self._plain = strip_tags(self.body)
        return self._plain

    @property
    def from_(self):
        if self.drip_base.from_email_name:
            from_ = "%s <%s>" % (self.drip_base.from_email_name, self.drip_base.from_email)
        else:
            from_ = self.drip_base.from_email
        return from_

    @property
    def message(self):
        if not self._message:

            self._message = EmailMultiAlternatives(
                self.subject, self.plain, self.from_, [self.user.email])

            # check if there are html tags in the rendered template
            if len(self.plain) != len(self.body):
                self._message.attach_alternative(self.body, 'text/html')
        return self._message


class DripBase(object):
    """
    A base object for defining a Drip.

    You can extend this manually, or you can create full querysets
    and templates from the admin.
    """
    #: needs a unique name
    name = None
    subject_template = None
    body_template = None
    from_email = None
    from_email_name = None

    def __init__(self, drip_model, *args, **kwargs):
        self.drip_model = drip_model

        self.name = kwargs.pop('name', self.name)
        self.from_email = kwargs.pop('from_email', self.from_email)
        self.from_email_name = kwargs.pop('from_email_name', self.from_email_name)
        self.subject_template = kwargs.pop('subject_template', self.subject_template)
        self.body_template = kwargs.pop('body_template', self.body_template)

        if not self.name:
            raise AttributeError('You must define a name.')

        self.now_shift_kwargs = kwargs.get('now_shift_kwargs', {})

    ##########################
    # ## DATE MANIPULATION ###
    ##########################

    def now(self):
        """
        This allows us to override what we consider "now", making it easy
        to build timelines of who gets what when.
        """
        return conditional_now() + self.timedelta(**self.now_shift_kwargs)

    def timedelta(self, *a, **kw):
        """
        If needed, this allows us the ability to manipuate the slicing of time.
        """
        from datetime import timedelta
        return timedelta(*a, **kw)

    def walk(self, into_past=0, into_future=0):
        """
        Walk over a date range and create new instances of self with new ranges.
        """
        walked_range = []
        for shift in range(-into_past, into_future):
            kwargs = dict(drip_model=self.drip_model,
                          name=self.name,
                          now_shift_kwargs={'days': shift})
            walked_range.append(self.__class__(**kwargs))
        return walked_range

    def apply_queryset_rules(self, qs):
        """
        First collect all filter/exclude kwargs and apply any annotations.
        Then apply all filters at once, and all excludes at once.
        """
        clauses = {
            'filter': [],
            'exclude': []}

        for rule in self.drip_model.queryset_rules.all():

            clause = clauses.get(rule.method_type, clauses['filter'])

            kwargs = rule.filter_kwargs(qs, now=self.now)
            clause.append(Q(**kwargs))

            qs = rule.apply_any_annotation(qs)

        if clauses['exclude']:
            qs = qs.exclude(functools.reduce(operator.or_, clauses['exclude']))
        qs = qs.filter(*clauses['filter'])

        return qs

    ###################
    # ## MANAGEMENT ###
    ###################

    def get_queryset(self):
        try:
            return self._queryset
        except AttributeError:
            self._queryset = self.apply_queryset_rules(self.queryset())\
                                 .distinct()
            return self._queryset

    def run(self):
        """
        Get the queryset, prune sent people, and send it.
        """
        if not self.drip_model.enabled:
            return None

        self.prune()
        count = self.send()

        return count

    def prune(self):
        """
        Do an exclude for all Users who have a SentDrip already.
        """
        target_user_ids = self.get_queryset().values_list('id', flat=True)
        exclude_user_ids = SentDrip.objects.filter(date__lt=conditional_now(),
                                                   drip=self.drip_model,
                                                   user__id__in=target_user_ids)\
                                           .values_list('user_id', flat=True)
        self._queryset = self.get_queryset().exclude(id__in=exclude_user_ids)

    def send(self):
        """
        Send the message to each user on the queryset.

        Create SentDrip for each user that gets a message.

        Returns count of created SentDrips.
        """

        if not self.from_email:
            self.from_email = getattr(settings, 'DRIP_FROM_EMAIL', settings.DEFAULT_FROM_EMAIL)
        MessageClass = message_class_for(self.drip_model.message_class)

        count = 0
        for user in self.get_queryset():
            message_instance = MessageClass(self, user)
            try:
                result = message_instance.message.send()
                if result:
                    SentDrip.objects.create(
                        drip=self.drip_model,
                        user=user,
                        from_email=self.from_email,
                        from_email_name=self.from_email_name,
                        subject=message_instance.subject,
                        # body=message_instance.body
                    )
                    count += 1
            except Exception as e:
                logging.error("Failed to send drip %s to user %s: %s" % (self.drip_model.id, user, e))

        return count

    #####################
    # ## USER DEFINED ###
    #####################

    def queryset(self):
        """
        Returns a queryset of auth.User who meet the
        criteria of the drip.

        Alternatively, you could create Drips on the fly
        using a queryset builder from the admin interface...
        """
        User = get_user_model()
        return User.objects


class MailgunBatchMessage(DripMessage):

    def __init__(self, drip_base):
        super(MailgunBatchMessage, self).__init__(drip_base=drip_base,
                                                  user=None)

    @staticmethod
    def map_variable(variable_name):
        return '%recipient.' + variable_name + '%'

    @property
    def context(self):
        """ Renders dict of type {'some_var': '%recipient.some_var%'} to be inserted into template
        Function for generating values is overridable by settings.MAILGUN['VARIABLE_GENERATION_FUNCTION']
        """
        f = self.drip_base.MAILGUN_VARIABLE_GENERATION_FUNCTION or self.map_variable
        if not self._context:
            self._context = Context({v: f(v) for v in self.drip_base.variables})
        return self._context

    def mailgun_variables_for_user(self, user, strict=True):
        """ Generates dict of type {'some_var': 42} for `user`.
        Mailgun will substitute these variables in place of %recipient.some_var%
        """

        def get_value(v):
            """ Get value of `v` variable for user given."""
            # try to get attribute from user
            obj = getattr(user, v, None)
            # if no, search for corresponding method in MailgunBatchMessage
            if not obj:
                obj = getattr(self, 'get_var_' + v, None)
                if obj:
                    obj = functools.partial(obj, user)

                # is there is no function to get var value raise or return empty string
                else:
                    if strict:
                        raise ValueError('There is no way to get `{0}` from user.'
                                         'user.{0} and MailgunBatchMessage.get_var_{0} tried'.format(v))
                    return ''

            return obj() if callable(obj) else obj

        vars = {v: get_value(v) for v in self.drip_base.variables}
        return vars

    def get_variables(self, qs=None, strict=True):
        """ Generates dict of type {<email>: <template variables>} for
        queryset of recipients"""
        qs = qs or self.drip_base.get_queryset()
        recipient_variables_dict = {u.email: self.mailgun_variables_for_user(u, strict)
                                    for u in qs if u.email}
        return recipient_variables_dict

    def get_var_text(self, user):
        return 'This is text from message instance'


class DripMailgun(DripBase):
    variables = ('full_name', 'text')

    MAILGUN_SECRET_API_KEY = settings.MAILGUN['SECRET_API_KEY']
    MAILGUN_DOMAIN = settings.MAILGUN['DOMAIN']

    MAILGUN_BATCHSIZE =\
        settings.MAILGUN.get('BATCHSIZE', 1000)
    MAILGUN_SEND_MESSAGE_ENDPOINT_TEMPLATE =\
        settings.MAILGUN.get('SEND_MESSAGE_ENDPOINT_TEMPLATE', 'https://api.mailgun.net/v3/{0}/messages')
    MAILGUN_YES_I_WANT_TO_SEND_MAILGUN_EMAIL_SERIOUSLY =\
        settings.MAILGUN.get('YES_I_WANT_TO_SEND_MAILGUN_EMAIL_SERIOUSLY', False)

    def __init__(self, *args, **kwargs):
        super(DripMailgun, self).__init__(*args, **kwargs)
        self.MAILGUN_VARIABLE_GENERATION_FUNCTION =\
            settings.MAILGUN.get('VARIABLE_GENERATION_FUNCTION', None)

    def get_message(self):
        m = MailgunBatchMessage(self)
        return m

    def send(self):
        if not self.from_email:
            self.from_email = getattr(settings, 'DRIP_FROM_EMAIL', settings.DEFAULT_FROM_EMAIL)
        m = self.get_message()

        mailgun.send_batch(
            subject=m.subject,
            template_html=m.body,
            template_plain=m.plain,

            # if email sending is serious, we dont want to raise errors
            # if variable not found
            recipient_variables_dict=m.get_variables(
                strict=not self.MAILGUN_YES_I_WANT_TO_SEND_MAILGUN_EMAIL_SERIOUSLY),

            from_email=m.from_,
            mailgun_api_key=self.MAILGUN_SECRET_API_KEY,
            mailgun_domain=self.MAILGUN_DOMAIN,
            mailgun_batchsize=self.MAILGUN_BATCHSIZE,
            url_template=self.MAILGUN_SEND_MESSAGE_ENDPOINT_TEMPLATE,
            YES_I_WANT_TO_SEND_MAILGUN_EMAIL_SERIOUSLY=self.MAILGUN_YES_I_WANT_TO_SEND_MAILGUN_EMAIL_SERIOUSLY,
        )
