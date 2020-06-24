# -*- coding: utf-8 -*-

from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    po_subscription_count = fields.Integer(string='Purchase Subscriptions', compute='_po_subscription_count')
    so_subscription_count = fields.Integer(string='Sale Subscriptions', compute='_so_subscription_count')

    @api.multi
    def _po_subscription_count(self):
        """ Compute the  number of subscription(s) """
        for partner in self:
            partner.po_subscription_count = self.env['subscription.service'].search_count([('partner_id', "=", partner.id), ('type','=','purchase')])
    @api.multi
    def _so_subscription_count(self):
        """ Compute the  number of subscription(s) """
        for partner in self:
            partner.so_subscription_count = self.env['subscription.service'].search_count([('partner_id', "=", partner.id), ('type','=','sale')])

    @api.multi
    def purchase_subscription_action_res_partner(self):
        """ Action on click on the stat button in partner form """
        for partner in self:
            return {
                "type": "ir.actions.act_window",
                "res_model": "subscription.service",
                "views": [[False, "tree"], [False, "form"]],
                "domain": [["partner_id", "=", partner.id],["type","=","purchase"]],
                "context": {"create": False},
                "name": "Purchase Subscriptions",
            }

    @api.multi
    def sale_subscription_action_res_partner(self):
        """ Action on click on the stat button in partner form """
        for partner in self:
            return {
                "type": "ir.actions.act_window",
                "res_model": "subscription.service",
                "views": [[False, "tree"], [False, "form"]],
                "domain": [["partner_id", "=", partner.id],["type","=","sale"]],
                "context": {"create": False},
                "name": "Sale Subscriptions",
            }
