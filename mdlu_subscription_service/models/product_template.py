# -*- coding: utf-8 -*-

from odoo import models, fields, api

class ProductTemplate(models.Model):
    _inherit = "product.template"

    po_subscription = fields.Boolean('Purchase Subscription')
    so_subscription = fields.Boolean('Sale Subscription')
