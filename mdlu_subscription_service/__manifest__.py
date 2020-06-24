# -*- coding: utf-8 -*-
{
    'name': "Subscription Services",

    'summary': """An easy way to manage your subscriptions and recurring payments.""",

    'description': """
        This module is used to trigger any recurring type of invoice :
            - rent
            - Telephone/ internet subscription
            - Any other regular payment that needs a recurrent invoice.
            - Customer subcriptions
                - Which also comes with a customer portal to help your customers
                  to view and manager their subscription.
    """,

    'author': "Moddulu Solutions",
    'license' : 'AGPL-3',
    'website': "https://www.moddulu.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/12.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Uncategorized',
    'version': '1.1',
    'images': ['static/description/banner.png',],

    # any module necessary for this one to work correctly
    'depends': [
        'base',
        'account',
        'analytic',
        'purchase',
        'sale',
        'sales_team',
        'portal',
    ],
    'price': 40.00,
    'currency': 'USD',

    # always loaded
    'data': [
        'data/subscription_service_data.xml',
        'data/ir_cron.xml',
        'security/ir.model.access.csv',
        'security/sale_subscription_security.xml',
        'views/assets.xml',
        'views/account_invoice_views.xml',
        'views/product_template_views.xml',
        'views/res_partner_views.xml',
        'views/subscription_service_views.xml',
        'views/subscription_portal_templates.xml',

    ],
}
