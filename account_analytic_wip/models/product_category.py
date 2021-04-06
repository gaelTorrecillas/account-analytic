# Copyright (C) 2021 Open Source Integrators
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).


from odoo import _, api, exceptions, fields, models


class ProductCategory(models.Model):
    _inherit = "product.category"

    property_cost_wip_journal_id = fields.Many2one(
        "account.journal",
        "Costing Journal",
        company_dependent=True,
        domain="[('company_id', '=', allowed_company_ids[0])]",
        check_company=True,
        help="When doing automated WIP valuation, this is the Accounting Journal "
        "in which entries will be automatically posted.",
    )
    property_cost_consume_account_id = fields.Many2one(
        "account.account",
        "Consumption Account",
        company_dependent=True,
        domain="[('company_id', '=', allowed_company_ids[0]), "
        "('deprecated', '=', False)]",
        check_company=True,
    )
    property_cost_wip_account_id = fields.Many2one(
        "account.account",
        "WIP Account",
        company_dependent=True,
        domain="[('company_id', '=', allowed_company_ids[0]), "
        "('deprecated', '=', False)]",
        check_company=True,
    )
    property_cost_variance_account_id = fields.Many2one(
        "account.account",
        "Variance Account",
        company_dependent=True,
        domain="[('company_id', '=', allowed_company_ids[0]), "
        "('deprecated', '=', False)]",
        check_company=True,
    )

    @api.constrains(
        "property_cost_wip_journal_id",
        "property_cost_consume_account_id",
        "property_cost_wip_account_id",
    )
    def _constrain_cost_config(self):
        for categ in self:
            wip_journal = categ.property_cost_wip_journal_id
            consume_account = categ.property_cost_consume_account_id
            wip_account = categ.property_cost_wip_account_id
            if any([wip_journal, consume_account, wip_account]) and not all(
                [wip_journal, consume_account, wip_account]
            ):
                raise exceptions.ValidationError(
                    _(
                        "Then configuring costing, a Journal "
                        " and account for Consumption,"
                        " WIP and Variance must be provided. "
                        "Check the configuration in Category %s."
                    )
                    % categ.display_name
                )

    def _get_accounting_data_for_costing(self, company=None):
        """
        Return the accounts and journal to use to post Journal Entries for
        the valuation of WIP costs and variances
        """
        self.ensure_one()
        if company:
            self = self.with_company(company)

        categ = self
        while categ.parent_id and not categ.property_cost_wip_journal_id:
            categ = categ.parent_id

        data = {}
        if categ.property_cost_wip_journal_id:
            data = {
                "journal": categ.property_cost_wip_journal_id,
                "consume_account": categ.property_cost_consume_account_id,
                "wip_account": categ.property_cost_wip_account_id,
                "variance_account": categ.property_cost_variance_account_id,
                "categ": categ,
            }
        return data
