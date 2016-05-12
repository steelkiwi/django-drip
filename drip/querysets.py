from django.db.models.query import QuerySet


class DripQueryset(QuerySet):

    def send(self, use_mailgun=True):
        for drip in self:
            drip = drip.drip_mailgun if use_mailgun else drip.drip
            drip.run()
