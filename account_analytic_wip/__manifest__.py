# Copyright (C) 2021 Open Source Integrators
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "Analytic Accounting support for WIP and Variances",
    "version": "14.0.1.0.0",
    "author": "Open Source Integrators, Odoo Community Association (OCA)",
    "summary": "Track and report WIP and Variances based on Analytic Item",
    "website": "https://github.com/OCA/account-analytic",
    "license": "AGPL-3",
    "depends": [
        "stock_account",
        "sale",  # TODO remove and still have tests pass?
    ],
    "category": "Accounting/Accounting",
    "data": [
        "security/ir.model.access.csv",
        "data/ir_cron_data.xml",
        "views/view_product_category.xml",
        "views/account_analytic_line.xml",
        "views/view_account_analytic_tracking.xml",
    ],
    "development_status": "Alpha",
    "maintainers": ["dreispt"],
    "installable": True,
}
