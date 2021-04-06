# Copyright (C) 2021 Open Source Integrators
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).


from odoo import api, fields, models


class AnalyticTrackingItem(models.Model):
    _name = "account.analytic.tracking.item"
    _description = "Cost Tracking Item"

    name = fields.Char(compute="_compute_name", store=True)
    date = fields.Date(default=fields.Date.today())
    analytic_id = fields.Many2one(
        "account.analytic.account",
        string="Analytic Account",
        required=True,
        ondelete="restrict",
    )
    product_id = fields.Many2one(
        "product.product", string="Cost Product", ondelete="restrict"
    )
    analytic_line_ids = fields.One2many(
        "account.analytic.line",
        "analytic_tracking_item_id",
        string="Analytic Items",
        help="Related analytic items with the project actuals.",
    )
    state = fields.Selection(
        [
            ("open", "Open"),
            ("done", "Done"),
            ("close", "Closed"),
            ("cancel", "Cancelled"),
        ],
        default="open",
        help="Open operations are in progress, no negative variances are computed. "
        "Done operations are completed, negative variances are computed. "
        "Closed operations are done and posting, no more actions to do.",
    )
    calculate = fields.Boolean(compute="_compute_calculate", store=True)

    parent_id = fields.Many2one(
        "account.analytic.tracking.item", "Parent Tracking Item", ondelete="cascade"
    )
    child_ids = fields.One2many(
        "account.analytic.tracking.item", "parent_id", string="Child Tracking Items"
    )

    # Planned Amount
    planned_amount = fields.Float()

    # Actual Amounts
    actual_amount = fields.Float(
        compute="_compute_actual_amounts",
        help="Total cost amount of the related Analytic Items. "
        "These Analytic Items are generated when a cost is incurred, "
        "and will later generated WIP and Variance Journal Entries.",
    )
    wip_actual_amount = fields.Float(
        compute="_compute_actual_amounts",
        help="Actual amount incurred below the planned amount limit.",
    )
    variance_actual_amount = fields.Float(
        compute="_compute_actual_amounts",
        help="Actual amount incurred above the planned amount limit.",
    )
    remaining_actual_amount = fields.Float(
        compute="_compute_actual_amounts",
        help="Actual amount planned and not yet consumed.",
    )
    pending_amount = fields.Float(
        compute="_compute_actual_amounts",
        help="Amount not yet posted to journal entries.",
    )

    # Accounted Amounts
    accounted_amount = fields.Float(
        help="Amount accounted in Journal Entries. "
        "Directly set by the routine creating the Journal Entries, "
        "and not directly read from the jpunral items."
    )
    wip_accounted_amount = fields.Float(
        help="Accounted amount incurred below the planned amount limit."
    )
    variance_accounted_amount = fields.Float(
        help="Accounted amount incurred above the planned amount limit."
    )

    @api.depends("product_id")
    def _compute_name(self):
        for item in self:
            item.name = item.product_id.display_name

    @api.depends("state", "parent_id", "child_ids")
    def _compute_calculate(self):
        for tracking in self:
            tracking.calculate = tracking.state != "cancel" and (
                tracking.parent_id or not tracking.child_ids
            )

    @api.depends(
        "analytic_line_ids.amount",
        "planned_amount",
        "accounted_amount",
        "state",
        "child_ids",
    )
    def _compute_actual_amounts(self):
        for item in self:
            # Actuals
            if not item.calculate:
                item.actual_amount = 0
            else:
                if item.parent_id:
                    actuals = item.parent_id.analytic_line_ids.filtered(
                        lambda x: x.product_id == item.product_id
                    )
                else:
                    actuals = item.analytic_line_ids
                item.actual_amount = -sum(actuals.mapped("amount")) or 0.0

            item.pending_amount = item.actual_amount - item.accounted_amount
            item.wip_actual_amount = min(item.actual_amount, item.planned_amount)

            if not item.calculate:
                item.remaining_actual_amount = 0
                item.variance_actual_amount = 0
                item.pending_amount = 0
            elif item.state == "open":
                # Negative variances show in the Remaining column
                item.remaining_actual_amount = (
                    item.planned_amount - item.wip_actual_amount
                )
                item.variance_actual_amount = max(
                    item.actual_amount - item.planned_amount, 0
                )
            else:
                # Negative variances show in the Variance column
                item.remaining_actual_amount = 0
                item.variance_actual_amount = item.actual_amount - item.planned_amount

    def _get_accounting_data_for_costing(self, company=None):
        self.ensure_one()
        return self.product_id.categ_id._get_accounting_data_for_costing()

    def _prepare_account_move(self, journal):
        date = self.env.context.get(
            "force_period_date", fields.Date.context_today(self)
        )
        description = self.display_name
        return {
            "journal_id": journal.id,
            "date": date,
            "ref": description,
            "move_type": "entry",
        }

    def _prepare_account_move_line(self, debit_amount, credit_amount, account):
        self.ensure_one()
        vals = {}
        if debit_amount or credit_amount:
            debit = (debit_amount if debit_amount > 0 else 0) + (
                -credit_amount if credit_amount < 0 else 0
            )
            credit = (credit_amount if credit_amount > 0 else 0) + (
                -debit_amount if debit_amount < 0 else 0
            )
            vals = {
                "name": self.display_name,
                "product_id": self.product_id.id,
                "product_uom_id": self.product_id.uom_id.id,
                "analytic_account_id": self.analytic_id.id,
                "ref": self.display_name,
                "account_id": account.id,
                "debit": debit,
                "credit": credit,
            }
        return vals

    def _create_jornal_entry(self, wip_amount, var_amount):
        self.ensure_one()
        if wip_amount or var_amount:
            accounts = self._get_accounting_data_for_costing()
            move_lines = [
                self._prepare_account_move_line(wip_amount, 0, accounts["wip_account"]),
                self._prepare_account_move_line(
                    var_amount, 0, accounts["variance_account"]
                ),
            ]
            if var_amount < 0:
                move_lines.extend(
                    [
                        self._prepare_account_move_line(
                            0, wip_amount, accounts["consume_account"]
                        ),
                        self._prepare_account_move_line(
                            0, var_amount, accounts["consume_account"]
                        ),
                    ]
                )
            else:
                move_lines.append(
                    self._prepare_account_move_line(
                        0, wip_amount + var_amount, accounts["consume_account"]
                    )
                )
            je_vals = self._prepare_account_move(accounts["journal"])
            je_vals["line_ids"] = [(0, 0, x) for x in move_lines if x]
            je_new = self.env["account.move"].sudo().create(je_vals)
            je_new._post()
            # Update Analytic lines with the Consumption journal item
            consume_move = je_new.line_ids.filtered(
                lambda x: x.account_id == accounts["consume_account"]
            )
            self.analytic_line_ids.write({"move_id": consume_move[:1].id})

    def _process_wip_and_variance(self):
        """
        For each Analytic Tracking Item with a Pending Amount different from zero,
        generate Journal Entries for WIP and excess Variances
        """
        for item in self.filtered("pending_amount"):
            # TODO: use float_compare()
            wip_pending = round(item.wip_actual_amount - item.wip_accounted_amount, 6)
            var_pending = round(
                item.variance_actual_amount - item.variance_accounted_amount, 6
            )
            item._create_jornal_entry(wip_pending, var_pending)
            # Update accounted amount to equal actual amounts
            item.accounted_amount = item.actual_amount
            item.wip_accounted_amount = item.wip_actual_amount
            item.variance_accounted_amount = item.variance_actual_amount
        # Once Done lines are posted, change them to Closed state
        self.filtered(lambda x: x.state == "done").write({"state": "close"})

    def process_wip_and_variance(self):
        """
        Generate Journal Entries for negative variances,
        when a an Analytic Tracking Item is set to Done
        """
        all_tracking = self | self.child_ids
        all_tracking._process_wip_and_variance()

    def _cron_process_wip_and_variance(self):
        items = self.search([("state", "not in", ["close", "cancel"])])
        items.process_wip_and_variance()

    def process_wip_and_variance_on_done(self):
        """
        Generate Journal Entries for negative variances,
        when a an Analytic Tracking Item is set to Done
        """
        all_tracking = self | self.child_ids
        all_tracking.write({"state": "done"})
        all_tracking._process_wip_and_variance()

    def action_cancel(self):
        # TODO: what to do if there are JEs done?
        all_tracking = self | self.child_ids
        all_tracking.write({"state": "cancel"})
