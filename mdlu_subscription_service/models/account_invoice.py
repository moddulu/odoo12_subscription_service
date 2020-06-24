# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from dateutil.relativedelta import relativedelta

class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    subscription_id = fields.Many2one('subscription.service', string="Subscription")

    @api.multi
    def action_invoice_cancel(self):
        for inv in self.filtered(lambda i: i.subscription_id != False and i.state == 'open'):
            sub = inv.subscription_id
            sub.recurring_next_date -= relativedelta(months=1)
            paid_inv_count = len(sub.invoice_ids.filtered(lambda i: i.state == 'paid'))
            current_date = sub.date_start + relativedelta(months=paid_inv_count)
            if sub.recurring_next_date < current_date:
                sub.recurring_next_date = current_date
            body = '%s has been cancelled on subscription %s.  A new invoice will be issued.' % (inv.number,sub.display_name)
            sub.message_post(body=body, message_type='comment',**{'subtype_id': 1})
        return super(AccountInvoice,self).action_invoice_cancel()
