odoo.define('mdlu_subscription_service.portal_subscription', function (require) {
    'use strict';

    require('web.dom_ready');
    if(!$('.oe_website_contract').length) {
        return $.Deferred().reject("DOM doesn't contain '.js_surveyresult'");
    }

    $('.contract-submit').off('click').on('click', function () {
        $(this).attr('disabled', true);
        $(this).prepend('<i class="fa fa-refresh fa-spin"></i> ');
        $(this).closest('form').submit();
    });
});
