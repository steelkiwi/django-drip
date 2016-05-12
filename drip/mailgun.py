import json
from pprint import pprint


def chunks(xs, size):
    for i in range(0, len(xs), size):
        yield xs[i:i+size]


def email_is_valid(email):
    return '.' in email and '@' in email


def mock_post(*args, **kwargs):
    print('\n\n########### HERE IS NEW REQUEST ############')
    pprint(args)
    pprint(kwargs)


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
        url_template='https://api.mailgun.net/v3/{0}/messages'):

    # validations
    if not isinstance(recipient_variables_dict, dict):
        raise TypeError('Should be dict as described in https://documentation.mailgun.com/user_manual.html#batch-sending')  # NOQA
    for email, variables in recipient_variables_dict.items():
        if email_is_valid(email) and isinstance(variables, dict):
            continue
        raise TypeError('Should be dict as described in https://documentation.mailgun.com/user_manual.html#batch-sending')  # NOQA

    # common params
    url = url_template.format(mailgun_domain)
    auth = ('api', mailgun_api_key)

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

        post(url, auth=auth, data=data)
