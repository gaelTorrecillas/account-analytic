# Copyright (C) 2021 Open Source Integrators
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).


from odoo import _, api, fields, models


class AnalyticTrackingItem(models.Model):
    """
    Tracking Items provide a central point to report WIP and Variances.
    Expected amounts are stored on a key event, such a confirming an order.
    Done amounts are captured by Analytic items.
    They can then be posted as journal entries.
    """

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
    activity_cost_id = fields.Many2one("activity.cost.rule", "Activity Cost Rule")

    # Related calculated data
    company_id = fields.Many2one(
        "res.company", related="analytic_id.company_id", store=True
    )
    product_categ_id = fields.Many2one(
        "product.category", related="product_id.categ_id", store=True
    )
    # Analytic Items, to compute WIP actuals from
    analytic_line_ids = fields.One2many(
        "account.analytic.line",
        "analytic_tracking_item_id",
        string="Analytic Items",
        help="Related analytic items with the project actuals.",
    )
    # Journal Entries, to compute Posted actuals from
    account_move_ids = fields.One2many(
        "account.move",
        "analytic_tracking_item_id",
        string="Journal Entries",
        help="Related journal entries with the posted WIP.",
    )
    state = fields.Selection(
        [
            ("draft", "Open"),  # In progress
            ("done", "Done"),  # Completed and Posted
            ("cancel", "Cancelled"),
        ],
        default="draft",
        help="Open operations are in progress, no negative variances are computed. "
        "Done operations are completed, negative variances are computed. "
        "Locked operations are done and posted, no more actions to do.",
    )
    to_calculate = fields.Boolean(compute="_compute_to_calculate")

    parent_id = fields.Many2one(
        "account.analytic.tracking.item", "Parent Tracking Item", ondelete="cascade"
    )
    child_ids = fields.One2many(
        "account.analytic.tracking.item", "parent_id", string="Child Tracking Items"
    )

    # Planned Amount
    planned_qty = fields.Float()
    planned_amount = fields.Float()

    # Actual Amounts
    actual_amount = fields.Float(
        compute="_compute_actual_amounts",
        store=True,
        help="Total cost amount of the related Analytic Items. "
        "These Analytic Items are generated when a cost is incurred, "
        "and will later generated WIP and Variance Journal Entries.",
    )
    wip_actual_amount = fields.Float(
        compute="_compute_actual_amounts",
        store=True,
        help="Actual amount incurred below the planned amount limit.",
    )
    variance_actual_amount = fields.Float(
        compute="_compute_actual_amounts",
        store=True,
        help="Actual amount incurred above the planned amount limit.",
    )
    remaining_actual_amount = fields.Float(
        compute="_compute_actual_amounts",
        store=True,
        help="Actual amount planned and not yet consumed.",
    )
    pending_amount = fields.Float(
        compute="_compute_actual_amounts",
        store=True,
        help="Amount not yet posted to journal entries.",
    )

    # Accounted Amounts
    accounted_amount = fields.Float(
        help="Amount accounted in Journal Entries. "
        "Directly set by the routine creating the Journal Entries, "
        "and not directly read from the jpunral items."
    )

    @api.depends("product_id")
    def _compute_name(self):
        for item in self:
            item.name = item.product_id.display_name

    @api.depends("state", "child_ids")
    def _compute_to_calculate(self):
        for item in self:
            item.to_calculate = item.state != "cancel"

    @api.depends(
        "analytic_line_ids.amount",
        "parent_id.analytic_line_ids.amount",
        "planned_amount",
        "accounted_amount",
        "state",
        "child_ids",
    )
    def _compute_actual_amounts(self):
        for item in self:
            actual = 0.0
            to_post = 0.0
            wip = 0.0
            var = 0.0
            remain = 0.0
            if item.state != "cancel" and not item.child_ids:
                doing = item.state in ("draft")
                planned = item.planned_amount
                actual = -sum(
                    x.amount_abcost if x.parent_id else x.amount
                    for x in item.analytic_line_ids
                )
                to_post = actual - item.accounted_amount
                wip = min(actual, planned)
                dif = actual - planned
                remain = -dif if doing and dif <= 0.0 else 0.0
                var = dif if not remain else 0.0

            item.actual_amount = actual
            item.pending_amount = to_post
            item.wip_actual_amount = wip
            item.variance_actual_amount = var
            item.remaining_actual_amount = remain

    def _prepare_account_move_head(self, journal, move_lines=None):
        return {
            "journal_id": journal.id,
            "date": self.env.context.get(
                "force_period_date", fields.Date.context_today(self)
            ),
            "ref": self.display_name,
            "move_type": "entry",
            "analytic_tracking_item_id": self.id,
            "line_ids": [(0, 0, x) for x in move_lines or [] if x],
        }

    def _prepare_account_move_line(self, account, amount, clear_account=None):
        # Note: do not set analytic_account_id,
        # as that triggers a (repeated) Analytic Item
        return {
            "name": _("WIP %s") % (self.display_name),
            "product_id": self.product_id.id,
            "product_uom_id": self.product_id.uom_id.id,
            "ref": self.display_name,
            "account_id": account.id,
            "debit": amount if amount > 0.0 else 0.0,
            "credit": -amount if amount < 0.0 else 0.0,
            "clear_wip_account_id": clear_account.id if clear_account else None,
        }

    def _get_accounting_data_for_valuation(self):
        """
        Extension hook to set the accounts to use
        Returns a dict including the keys:
        - "stock_valuation": for applied work account
        - "stock_input": for WIP account
        - "stock_output": for WIP clearing account
        - "stock_journal": the journal to use
        """
        return self.product_id.product_tmpl_id.get_product_accounts()

    def _create_wip_journal_entry(self):
        accounts = self._get_accounting_data_for_valuation()
        wip_journal = accounts["stock_journal"]
        amount = self.pending_amount
        # FIXME: missing WIP tracking items without Product!
        if amount and wip_journal:
            acc_clear_wip = accounts["stock_output"]
            acc_debit = accounts["stock_input"]
            acc_credit = accounts["stock_valuation"]
            move_lines = [
                self._prepare_account_move_line(acc_debit, amount, acc_clear_wip),
                self._prepare_account_move_line(acc_credit, -amount),
            ]
            je_vals = self._prepare_account_move_head(wip_journal, move_lines)
            je_new = self.env["account.move"].sudo().create(je_vals)
            je_new._post()
            return je_new

    def _prepare_clear_wip_journal_entries(self):
        """
        Returns a list of move line values, and the journal to use.
        Will clear the balance of the Journal Items
        linked to the Tracking Item and with a Clear Account set.
        """
        self and self.ensure_one()
        je_lines = self.mapped("account_move_ids.line_ids")
        wip_je_lines = je_lines.filtered("clear_wip_account_id")
        accounts = wip_je_lines.mapped("account_id")
        clear_accounts = wip_je_lines.mapped("clear_wip_account_id")

        move_lines = []
        for account, clear_account in zip(accounts, clear_accounts):
            wip_lines = wip_je_lines.filtered(
                lambda x: x.account_id == account
                and x.clear_wip_account_id == clear_account
            )
            wip_amount = sum(wip_lines.mapped("balance"))
            if wip_amount:
                move_lines.append(self._prepare_account_move_line(account, -wip_amount))
                move_lines.append(
                    self._prepare_account_move_line(clear_account, wip_amount)
                )

        wip_journal = wip_je_lines[:1].move_id.journal_id
        return move_lines, wip_journal

    def clear_wip_journal_entries(self):
        """
        Clear the WIP accounts so that their balance is zero
        and Debit the final Output account.
        """
        AccountMove = self.env["account.move"].sudo()
        for tracked in self:
            move_lines, wip_journal = tracked._prepare_clear_wip_journal_entries()
            if move_lines:
                je_vals = tracked._prepare_account_move_head(wip_journal, move_lines)
                je_new = AccountMove.create(je_vals)
                je_new._post()

    def process_wip_and_variance(self, close=False):
        """
        For each Analytic Tracking Item with a Pending Amount different from zero,
        generate Journal Entries for WIP and excess Variances
        """
        all_tracking = self | self.child_ids
        if close:
            # Set to done, to have negative variances computed
            all_tracking.write({"state": "done"})
        for item in all_tracking:
            is_posted = item._create_wip_journal_entry()
            if is_posted:
                # Update accounted amount to equal actual amounts
                item.accounted_amount = item.actual_amount

    def _cron_process_wip_and_variance(self):
        items = self.search([("state", " in", ["draft"])])
        items.process_wip_and_variance()

    def action_cancel(self):
        # TODO: what to do if there are JEs done?
        all_tracking = self | self.child_ids
        all_tracking.write({"state": "cancel"})

    def _get_unit_cost(self):
        self.ensure_one()
        unit_cost = 0.0
        if self.product_id:
            unit_cost = self.product_id.price_compute(
                "standard_price", uom=self.product_id.uom_id
            )[self.product_id.id]
        return unit_cost

    def _populate_abcost_tracking_item(self):
        to_calculate_with_childs = (self | self.child_ids).filtered("to_calculate")
        for tracking in to_calculate_with_childs:
            cost_rules = tracking.product_id.activity_cost_ids
            # Calculate Planned Amount if no ABC an only qty provided
            # or when a ABC tracking (sub)item is created
            if not tracking.planned_amount and not cost_rules:
                factor = tracking.activity_cost_id.factor or 1.0
                unit_cost = tracking._get_unit_cost()
                qty = factor * (tracking.planned_qty or tracking.parent_id.planned_qty)
                tracking.planned_amount = qty * unit_cost
            # Generate ABC (sub)tracking items
            if cost_rules and not tracking.child_ids:
                for cost_rule in cost_rules:
                    vals = {
                        "parent_id": tracking.id,
                        "product_id": cost_rule.product_id.id,
                        "activity_cost_id": cost_rule.id,
                        "planned_qty": 0.0,
                    }
                    tracking.copy(vals)

    @api.model
    def create(self, vals):
        new = super().create(vals)
        new._populate_abcost_tracking_item()
        return new

    def write(self, vals):
        res = super().write(vals)
        # Write on planned_qty to update the planned amounts
        if vals.get("planned_qty"):
            self._populate_abcost_tracking_item()
        return res
