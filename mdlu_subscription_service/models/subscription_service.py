# -*- coding: utf-8 -*-

from dateutil.relativedelta import relativedelta
from datetime import datetime, timedelta
from odoo import api, fields, models, _
from odoo.exceptions import UserError
import odoo.addons.decimal_precision as dp
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT, DEFAULT_SERVER_DATE_FORMAT
import logging
_logger = logging.getLogger(__name__)

TYPE_ABBRV = {
    'purchase': 'PSUB',
    'sale': 'SSUB',
    '': 'SUB',
}

INV_TYPE = {
    'purchase': 'in_invoice',
    'sale': 'out_invoice',
}

PRODUCT_DOMAIN = {
    'purchase': 'po_subscription',
    'sale': 'so_subscription',
}

class SubscriptionService(models.Model):
    _name = 'subscription.service'
    _description = 'Subscription Service'
    _inherit = ['portal.mixin', 'mail.thread', 'mail.activity.mixin']

    @api.multi
    def _compute_invoice_count(self):
        """ Compute the number of invoices """
        for sub in self:
            sub.invoice_count = len(sub.invoice_ids)

    state = fields.Selection([('draft', 'New'),
                              ('open', 'In Progress'),
                              ('pending', 'To Renew'),
                              ('close', 'Closed'),
                              ('cancel', 'Cancelled')],
                             string='Status',
                             required=True, copy=False, default='draft')
    type = fields.Selection([('purchase','Purchase'),('sale','Sale')], default='purchase', required=True)
    date_start = fields.Date(string='Start Date', default=fields.Date.today)
    date_end = fields.Date(string="End Date",
            help="If set in advance, the subscription will be set to pending 1 month before the date and will be closed on the date set in this field.")
    partner_id = fields.Many2one('res.partner', string='Partner')
    recurring_invoice_line_ids = fields.One2many('subscription.service.line', 'subscription_serv_id', string='Invoice Lines', copy=True)
    recurrency = fields.Selection([('daily', 'Day(s)'), ('weekly', 'Week(s)'), ('monthly', 'Month(s)'), ('yearly', 'Year(s)')],
            string='Recurrency', help="Invoice automatically repeat at specified interval", required=True, default='monthly')
    recurring_interval = fields.Integer(string='Repeat Every', help="Repeat every (Days/Week/Month/Year)", required=True, default=1)
    recurring_next_date = fields.Date(string='Date of Next Invoice', default=fields.Date.today,
            help="The next invoice will be created on this date then the period will be extended.")
    recurring_total = fields.Float(compute='_compute_recurring_total', string="Recurring Price", store=True)
    user_id = fields.Many2one('res.users', string='Sales Rep')
    invoice_ids = fields.One2many('account.invoice', 'subscription_id')
    invoice_count = fields.Integer(compute='_compute_invoice_count')
    code = fields.Char(string='Reference', index=True, readonly=True)
    currency_id = fields.Many2one('res.currency', string='Currency')
    payment_term_id = fields.Many2one('account.payment.term', string="Payment term")
    name = fields.Char(compute='_compute_name', store=True, readonly=True)
    company_id = fields.Many2one('res.company', string="Company", required="True", default=lambda self: self.env.user.company_id)
    description = fields.Text()
    recurring_amount_tax = fields.Monetary(string='Taxes', store=True, readonly=True, compute='_compute_recurring_total')
    amount_untaxed = fields.Monetary(string='Untaxed Total', store=True, readonly=True, compute='_compute_recurring_total')

    @api.depends('recurring_invoice_line_ids')
    def _compute_recurring_total(self):
        """ Compute the reccuring price of the subscription """
        for sub in self:
            amount_untaxed = amount_tax = 0.0
            for line in sub.recurring_invoice_line_ids:
                amount_untaxed += line.subtotal
                amount_tax += line.price_tax
            sub.amount_untaxed = amount_untaxed
            sub.recurring_amount_tax = amount_tax
            sub.recurring_total = amount_untaxed + amount_tax


    @api.depends('code', 'partner_id','type')
    def _compute_name(self):
        """ Get the name of the subscription : Sub.type - reference - provider """
        for sub in self:
            sub.name = '%s - %s' % (sub.code, sub.partner_id.name)

    @api.onchange('partner_id')
    def get_info_partner(self):
        """ Get all the information about the partner """
        for sub in self:
            currency = False
            payment_term = False
            if sub.company_id:
                currency = sub.company_id.currency_id
            if sub.partner_id:
                if sub.partner_id.property_purchase_currency_id:
                    currency = sub.partner_id.property_purchase_currency_id
                elif sub.partner_id.property_product_pricelist:
                    currency = sub.partner_id.property_product_pricelist.currency_id
                if sub.partner_id.property_supplier_payment_term_id:
                    payment_term = sub.partner_id.property_supplier_payment_term_id
            sub.currency_id = currency
            sub.payment_term_id = payment_term

    @api.model
    def _set_code(self, type):
        seq = ''
        abbrv = TYPE_ABBRV[type] #if self.type else 'SUB'
        if self.code and '-' in self.code:
            seq = self.code.split('-')[1]
        if not seq:
            seq = self.env['ir.sequence'].next_by_code('subscription.service')
        return '%s-%s' % (abbrv, seq) if seq else abbrv

    @api.model
    def create(self, vals):
        """ Set the reference of the subscription before creation """
        vals['code'] = self._set_code(vals['type'])
        if vals.get('name', 'New') == 'New':
            vals['name'] = vals['code']
        return super(SubscriptionService, self).create(vals)

    @api.multi
    def write(self,vals):
        rec = super(SubscriptionService, self).write(vals)
        if self.code and '-' in self.code:
            abbrv = self.code.split('-')[0]
            if abbrv != TYPE_ABBRV[self.type]:
                self.code = self._set_code(self.type)
        return rec

    #define button for viewing the invoices
    @api.multi
    def action_view_invoice(self):
        invoices = self.mapped('invoice_ids')
        action = self.env.ref('account.action_invoice_tree1').read()[0]
        if len(invoices) > 1:
            action['domain'] = [('id', 'in', invoices.ids)]
        elif len(invoices) == 1:
            if self.type == 'purchase':
                action['views'] = [(self.env.ref('account.invoice_supplier_form').id, 'form')]
            elif self.type == 'sale':
                action['views'] = [(self.env.ref('account.invoice_form').id, 'form')]
            action['res_id'] = invoices.ids[0]
        else:
            action = {'type': 'ir.actions.act_window_close'}
        return action

    @api.model
    def cron_subscription_service(self):
        """ Compute the end of the subscription """
        today = fields.Date.today()
        next_month = fields.Date.to_string(today + relativedelta(months=1))

        # set to pending if date is in less than a month
        domain_pending = [('date_end', '<', next_month), ('state', '=', 'open')]
        subscriptions_pending = self.search(domain_pending)
        subscriptions_pending.write({'state': 'pending'})

        # set to close if date is passed
        domain_close = [('date_end', '<', today),
                        ('state', 'in', ['pending', 'open'])]
        subscriptions_close = self.search(domain_close)
        subscriptions_close.write({'state': 'close'})

        return dict(pending=subscriptions_pending.ids, closed=subscriptions_close.ids)

    @api.model
    def _cron_recurring_create_invoice(self):
        """ If subscribed, create an invoice """
        return self._recurring_create_invoice(automatic=True)

    @api.multi
    def set_open(self):
        """ Set the subscription status to 'open' """
        return self.write({'state': 'open'})

    @api.multi
    def set_pending(self):
        """ Set the subscription status to 'pending' """
        return self.write({'state': 'pending'})

    @api.multi
    def set_cancel(self):
        """ Set the subscription status to 'cancel' """
        return self.write({'state': 'cancel'})

    @api.multi
    def set_close(self):
        """ Set the subscription status to 'close' """
        return self.write({'state': 'close', 'date_end': fields.Date.from_string(fields.Date.today())})

    @api.multi
    def _prepare_invoice_data(self):
        """ Prepare the data of the invoice """
        self.ensure_one()

        if not self.partner_id:
            raise UserError(
                _("You must first select a Customer for Subscription %s!") % self.name)

        """ Get the fiscal position of the company """
        fpos_id = self.env['account.fiscal.position'].with_context(
            force_company=self.company_id.id).get_fiscal_position(self.partner_id.id)
        """ Get the subscription journal of the company """
        journal = self.env['account.journal'].search(
            [('type', '=', self.type), ('company_id', '=', self.company_id.id)], limit=1)
        if not journal:
            raise UserError(_('Please define a %s journal for the company "%s".') % (self.type, self.company_id.name or '', ))

        next_date = fields.Date.from_string(self.recurring_next_date)
        periods = {'daily': 'days', 'weekly': 'weeks',
                   'monthly': 'months', 'yearly': 'years'}
        new_date = next_date + \
            relativedelta(
                **{periods[self.recurrency]: self.recurring_interval})

        return {
            'account_id': self.partner_id.property_account_payable_id.id,
            'type': INV_TYPE[self.type],
            'partner_id': self.partner_id.id,
            'journal_id': journal.id,
            'date_invoice': self.recurring_next_date,
            'origin': self.code,
            'fiscal_position_id': fpos_id,
            'currency_id': self.currency_id and self.currency_id.id or False,
            'payment_term_id': self.payment_term_id and self.payment_term_id.id
                                or self.partner_id.property_supplier_payment_term_id.id,
            'company_id': self.company_id.id,
            'comment': _("This invoice covers the following period: %s - %s") % (next_date, new_date),
        }

    @api.multi
    def _prepare_invoice_line(self, line, fiscal_position):
        """ Prepare the invoice line """
        account_id = line.product_id.property_account_expense_id.id
        if not account_id:
            account_id = line.product_id.categ_id.property_account_expense_categ_id.id
        account_id = fiscal_position.map_account(account_id)

        tax = self.env['account.tax']
        if 'purchase' == line.subscription_serv_id.type:
            tax = line.product_id.supplier_taxes_id.filtered(lambda r: r.company_id == line.subscription_serv_id.company_id)
        elif 'sale' == line.subscription_serv_id.type:
            tax = line.product_id.taxes_id.filtered(lambda r: r.company_id == line.subscription_serv_id.company_id)
        tax = fiscal_position.map_tax(tax)
        return {
            'name': line.name,
            'account_id': account_id,
            'account_analytic_id': line.analytic_account_id.id,
            'analytic_tag_ids': [(6, 0, line.analytic_tag_ids.ids)],
            'price_unit': line.unit_price or 0.0,
            'discount': line.discount,
            'quantity': line.qty,
            'uom_id': line.uom_id.id,
            'product_id': line.product_id.id,
            'invoice_line_tax_ids': [(6, 0, tax.ids)],
        }

    @api.multi
    def _prepare_invoice_lines(self, fiscal_position):
        """ Prepare the invoice lines """
        self.ensure_one()
        fiscal_position = self.env[
            'account.fiscal.position'].browse(fiscal_position)
        return [(0, 0, self._prepare_invoice_line(line, fiscal_position)) for line in self.recurring_invoice_line_ids]

    @api.multi
    def _prepare_invoice(self):
        """ Prepare the invoice """
        invoice = self._prepare_invoice_data()
        invoice['invoice_line_ids'] = self._prepare_invoice_lines(
            invoice['fiscal_position_id'])
        return invoice

    @api.multi
    def recurring_invoice(self):
        """ Reccuring the invoice """
        self._recurring_create_invoice()
        return self.action_subscription_invoice()

    @api.multi
    def action_subscription_invoice(self):
        """ Show the invoices views """
        views = []
        if 'purchase' == self.type:
            views = [[self.env.ref('account.invoice_supplier_tree').id, "tree"],
                      [self.env.ref('account.invoice_supplier_form').id, "form"]]
        elif 'sale' == self.type:
            views = [[self.env.ref('account.invoice_tree').id, "tree"],
                      [self.env.ref('account.invoice_form').id, "form"]]
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.invoice",
            "views": views,
            "domain": [["id", "in", self.invoice_ids.ids]],
            "context": {"create": False},
            "name": "Invoices",
        }

    @api.returns('account.invoice')
    def _recurring_create_invoice(self, automatic=False):
        AccountInvoice = self.env['account.invoice']
        invoices = self.env['account.invoice']
        current_date = fields.Date.today()
        periods = {'daily': 'days', 'weekly': 'weeks',
                   'monthly': 'months', 'yearly': 'years'}
        domain = [('id', 'in', self.ids)] if self.ids else [
            ('recurring_next_date', '<=', current_date), ('state', '=', 'open')]
        sub_data = self.search_read(fields=['id', 'company_id'], domain=domain)
        for company_id in set(data['company_id'][0] for data in sub_data):
            sub_ids = map(lambda s: s['id'], filter(
                lambda s: s['company_id'][0] == company_id, sub_data))
            subs = self.with_context(
                company_id=company_id, force_company=company_id).browse(sub_ids)
            for sub in subs:
                try:
                    invoices |= AccountInvoice.create(sub._prepare_invoice())
                    sub.invoice_ids = [(4, invoices[-1].id, _)]
                    invoices[-1].compute_taxes()
                    if sub.payment_term_id:
                        invoices[-1].write({'payment_term_id': sub.payment_term_id.id})
                    next_date = fields.Date.from_string(
                        sub.recurring_next_date or current_date)
                    rule, interval = sub.recurrency, sub.recurring_interval
                    new_date = next_date + \
                        relativedelta(**{periods[rule]: interval})
                    sub.write({'recurring_next_date': new_date})
                    if automatic:
                        self.env.cr.commit()
                    body = 'A new invoice has been created for subscription %s' % (sub.display_name)
                    sub.message_post(body=body, message_type='comment',**{'subtype_id': 1})
                except Exception:
                    if automatic:
                        self.env.cr.rollback()
                        _logger.exception(
                            'Fail to create recurring invoice for subscription %s', sub.code)
                    else:
                        raise
        invoices.action_invoice_open()
        return invoices

    @api.multi
    def increment_period(self):
        """ Get the date of the next occurrence """
        for account in self:
            current_date = account.recurring_next_date or self.default_get(
                ['recurring_next_date'])['recurring_next_date']
            periods = {'daily': 'days', 'weekly': 'weeks',
                       'monthly': 'months', 'yearly': 'years'}
            new_date = fields.Date.from_string(current_date) + relativedelta(
                **{periods[account.recurrency]: account.recurring_interval})
            account.write({'recurring_next_date': new_date})




class SubscriptionServiceLine(models.Model):
    _name = 'subscription.service.line'
    _description = 'Subscription Service Line'

    @api.onchange('product_id')
    def _compute_unit_price(self):
        partner_id = self.subscription_serv_id.partner_id
        pricelist = partner_id.property_product_pricelist if partner_id.property_product_pricelist else False
        item_price = 0.0
        if 'sale' == self.sub_type:
            item_price = self.product_id.list_price
        elif 'purchase' == self.sub_type:
            item_price = self.product_id.standard_price
        if pricelist and self.product_id and 'sale' == self.sub_type:
            item_price = pricelist.get_products_price(self.product_id,[self.qty],partner_id)[self.product_id.id]
        elif 'purchase' == self.sub_type and partner_id in self.product_id.seller_ids.mapped('name'):
            item_price = list(filter(lambda x: x.name == partner_id, self.product_id.seller_ids))[0].price
        self.unit_price = item_price
        if 'sale' == self.sub_type:
            self.sub_line_tax_ids |= self.product_id.taxes_id
        elif 'purchase' ==  self.sub_type:
            self.sub_line_tax_ids |= self.product_id.supplier_taxes_id

    @api.depends('unit_price', 'qty', 'discount','sub_line_tax_ids')
    def _compute_subtotal(self):
        """ Compute the subtotal price """
        for line in self:
            subtotal = line.qty * line.unit_price * (100.0 - line.discount) / 100.0
            taxes = line.sub_line_tax_ids.compute_all(subtotal, line.subscription_serv_id.currency_id, line.qty, product=line.product_id, partner=line.subscription_serv_id.partner_id)
            line.subtotal = subtotal
            line.price_tax = sum(t.get('amount', 0.0) for t in taxes.get('taxes', [])) if line.sub_type == 'sale' else 0.0

    subscription_serv_id = fields.Many2one('subscription.service', string="Subscription", required=True)
    name = fields.Text(string='Description', required=True)
    sub_type = fields.Selection(related='subscription_serv_id.type')
    product_id = fields.Many2one('product.product', string='Product',required=True)
    qty = fields.Float(string='Quantity')
    uom_id = fields.Many2one('uom.uom',string='Unit of Measure', related='product_id.uom_id')
    unit_price = fields.Float(string='Unit Price')
    subtotal = fields.Float(string='Subtotal', compute='_compute_subtotal' )
    discount = fields.Float(string='Discount (%)', digits=dp.get_precision('Discount'))
    analytic_account_id = fields.Many2one('account.analytic.account', string="Analytic account")
    analytic_tag_ids = fields.Many2many('account.analytic.tag', string='Analytic Tags')
    sub_line_tax_ids = fields.Many2many('account.tax', string='Taxes', domain=['|', ('active', '=', False), ('active', '=', True)])
    price_tax = fields.Float(compute='_compute_subtotal', string='Total Tax', readonly=True, store=True)

    @api.onchange('product_id')
    def set_product_domain(self):
        product_ids = []
        sub_type = self._context.get('type')
        if sub_type:
            product_ids = self.env['product.product'].search([(PRODUCT_DOMAIN[sub_type],'=', True)]).mapped('id')
        return {'domain': {'product_id': [('id', 'in', product_ids)],},}
