# Copyright (C) 2021 Open Source Integrators
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class AnalyticLine(models.Model):
    _inherit = "account.analytic.line"

    analytic_tracking_item_id = fields.Many2one(
        "account.analytic.tracking.item", string="Tracking Item"
    )

    def _set_tracking_item(self):
        """
        When creating a child Analytic Item,
        find the correct matching child Tracking Item
        """
        for item in self:
            if not item.parent_id:
                pass  # TODO: automatically assign a Tracking Item!
            else:
                tracking_childs = item.parent_id.analytic_tracking_item_id.child_ids
                tracking_item = tracking_childs.filtered(
                    lambda x: x.product_id == item.product_id
                )
                item.analytic_tracking_item_id = tracking_item
                if not tracking_item:
                    _logger.error(
                        "Analytic Item %s: could not find related Tracked Item",
                        item.display_name,
                    )

    @api.model
    def create(self, vals):
        new = super().create(vals)
        new._set_tracking_item()
        return new
