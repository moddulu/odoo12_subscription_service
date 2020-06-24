# -*- coding: utf-8 -*-
import datetime
from collections import OrderedDict
from dateutil.relativedelta import relativedelta
from werkzeug.exceptions import NotFound
from odoo import http
from odoo.http import request
from odoo.tools.translate import _

from odoo.addons.payment.controllers.portal import PaymentProcessing
from odoo.addons.portal.controllers.portal import get_records_pager, pager as portal_pager, CustomerPortal


class CustomerPortal(CustomerPortal):

    def _get_subscription_service_domain(self, partner):
        return [
            ('partner_id.id', 'in', [partner.id, partner.commercial_partner_id.id]),
            ('type','=','sale'),
        ]

    def _prepare_portal_layout_values(self):
        """ Add subscription details to main account page """
        values = super(CustomerPortal, self)._prepare_portal_layout_values()
        partner = request.env.user.partner_id
        values['subscription_count'] = request.env['subscription.service'].search_count(self._get_subscription_service_domain(partner))
        return values

    @http.route(['/my/subscriptions', '/my/subscriptions/page/<int:page>'], type='http', auth="user", website=True)
    def portal_my_subscriptions(self, page=1, date_begin=None, date_end=None, sortby=None, filterby=None, **kw):
        values = self._prepare_portal_layout_values()
        partner = request.env.user.partner_id
        SubscriptionService = request.env['subscription.service']

        domain = self._get_subscription_service_domain(partner)

        archive_groups = self._get_archive_groups('subscription.service', domain)
        if date_begin and date_end:
            domain += [('create_date', '>', date_begin), ('create_date', '<=', date_end)]

        searchbar_sortings = {
            'date': {'label': _('Newest'), 'order': 'create_date desc, id desc'},
            'name': {'label': _('Name'), 'order': 'name asc, id asc'}
        }
        searchbar_filters = {
            'all': {'label': _('All'), 'domain': []},
            'open': {'label': _('In Progress'), 'domain': [('state', '=', 'open')]},
            'pending': {'label': _('To Renew'), 'domain': [('state', '=', 'pending')]},
            'close': {'label': _('Closed'), 'domain': [('state', '=', 'close')]},
        }

        # default sort by value
        if not sortby:
            sortby = 'date'
        order = searchbar_sortings[sortby]['order']
        # default filter by value
        if not filterby:
            filterby = 'all'
        domain += searchbar_filters[filterby]['domain']

        # pager
        account_count = SubscriptionService.search_count(domain)
        pager = portal_pager(
            url="/my/subscriptions",
            url_args={'date_begin': date_begin, 'date_end': date_end, 'sortby': sortby, 'filterby': filterby},
            total=account_count,
            page=page,
            step=self._items_per_page
        )

        accounts = SubscriptionService.search(domain, order=order, limit=self._items_per_page, offset=pager['offset'])
        request.session['my_subscriptions_history'] = accounts.ids[:100]

        values.update({
            'accounts': accounts,
            'page_name': 'subscription',
            'pager': pager,
            'archive_groups': archive_groups,
            'default_url': '/my/subscriptions',
            'searchbar_sortings': searchbar_sortings,
            'sortby': sortby,
            'searchbar_filters': OrderedDict(sorted(searchbar_filters.items())),
            'filterby': filterby,
        })
        return request.render("mdlu_subscription_service.portal_my_subscriptions", values)

    @http.route(['/my/subscriptions/<int:subscription_id>'], type='http', auth="public", website=True)
    def portal_subscriptions_page(self, subscription_id, access_token=None, message=False, download=False, **kw):
        try:
            sbscr_sudo = self._document_check_access('subscription.service', subscription_id, access_token=access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')

        # use sudo to allow accessing/viewing orders for public user
        # only if he knows the private token
        now = datetime.date.today()

        # Log only once a day
        if sbscr_sudo and request.session.get('view_quote_%s' % sbscr_sudo.id) != now and request.env.user.share and access_token:
            request.session['view_quote_%s' % sbscr_sudo.id] = now
            body = _('Subscription viewed by customer')
            _message_post_helper(res_model='subscription.service', res_id=sbscr_sudo.id, message=body, token=sbscr_sudo.access_token, message_type='notification', subtype="mail.mt_note", partner_ids=sbscr_sudo.user_id.sudo().partner_id.ids)
        display_close = sbscr_sudo.state in ['open','pending']
        values = {
            'subscription_service': sbscr_sudo,
            'display_close': display_close,
            'message': message,
            'token': access_token,
            'return_url': '/shop/payment/validate',
            'bootstrap_formatting': True,
            'partner_id': sbscr_sudo.partner_id.id,
        }
        if sbscr_sudo.company_id:
            values['res_company'] = sbscr_sudo.company_id

        history = request.session.get('my_subscriptions_history', [])
        values.update(get_records_pager(history, sbscr_sudo))

        return request.render('mdlu_subscription_service.subscription', values)

    @http.route(['/my/subscription/<int:account_id>/close'], type='http', methods=["POST"], auth="public", website=True)
    def close_account(self, account_id, **kw):
        account = request.env['subscription.service'].browse(account_id)

        if kw.get('closing_text'):
                account.message_post(body=_('Closing text : ') + kw.get('closing_text'))
        account.set_close()
        account.date = datetime.date.today().strftime('%Y-%m-%d')
        return request.redirect('/my/home')
