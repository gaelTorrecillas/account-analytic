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

    def _prepare_tracking_item_values(self):
        return {
            "analytic_id": self.account_id.id,
            "product_id": self.product_id.id,
        }

    def populate_tracking_items(self):
        """
        When creating a child Analytic Item,
        find the correct matching child Tracking Item
        """
        TrackingItem = self.env["account.analytic.tracking.item"]
        missing_tracking = self.filtered(lambda x: not x.analytic_tracking_item_id)
        for item in missing_tracking:
            if not item.parent_id:
                vals = item._prepare_tracking_item_values()
                tracking_item = TrackingItem.create(vals)
                item.analytic_tracking_item_id = tracking_item
            if item.parent_id:
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
        new.populate_tracking_items()
        return new
