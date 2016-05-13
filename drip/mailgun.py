import json
from pprint import pprint

import requests

from django.core.validators import URLValidator, EmailValidator


def chunks(xs, size):
    for i in range(0, len(xs), size):
        yield xs[i:i+size]


def validate_email(email):
    EmailValidator()(email)


def validate_url(url):
    URLValidator()(url)


def mock_post(*args, **kwargs):
    return (args, kwargs)


def send_batch(
        # VVV mail data VVV
        subject,
        template_html,
        template_plain,
        recipient_variables_dict,
        from_email,
        # VVV mailgun setup VVV
        mailgun_api_key,
        mailgun_domain,
        mailgun_batchsize,
        post=mock_post,
        url_template=None,
        YES_I_WANT_TO_SEND_MAILGUN_EMAIL_SERIOUSLY=False):

    if YES_I_WANT_TO_SEND_MAILGUN_EMAIL_SERIOUSLY:
        post = requests.post

    # validations
    if not isinstance(recipient_variables_dict, dict):
        raise TypeError('Should be dict as described in https://documentation.mailgun.com/user_manual.html#batch-sending')  # NOQA
    for email, variables in recipient_variables_dict.items():
        validate_email(email)
        if isinstance(variables, dict):
            continue
        raise TypeError('Should be dict as described in https://documentation.mailgun.com/user_manual.html#batch-sending')  # NOQA
    validate_url(url_template)

    # common params
    url = url_template.format(mailgun_domain)
    auth = ('api', mailgun_api_key)

    responses = []

    # chunking and sending
    for chunk in chunks(recipient_variables_dict.items(), mailgun_batchsize):
        recipient_list = zip(*chunk)[0]
        recipient_variables = dict(chunk)

        data = {
            'subject': subject,
            'from': from_email,
            'to': recipient_list,
            'recipient-variables': json.dumps(recipient_variables)
        }
        if template_html:
            data['html'] = template_html
        if template_plain:
            data['text'] = template_plain

        r = post(url, auth=auth, data=data)
        responses.append(r)
    if post is mock_post:
        pprint(responses)
    return responses
