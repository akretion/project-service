# -*- coding: utf-8 -*-
###############################################################################
#
#   Module for OpenERP 
#   Copyright (C) 2012-TODAY Akretion (http://www.akretion.com).
#   @author Sébastien BEAU <sebastien.beau@akretion.com>
#           Benoît GUILLOT <benoit.guillot@akretion.com>
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
###############################################################################

from openerp.osv import fields, orm
import time
from tools.translate import _
import openerp.addons.decimal_precision as dp
from collections import defaultdict


class account_analytic_account(orm.Model):
    _inherit = 'account.analytic.account'

    _columns = {
        'invoice_uom_id': fields.many2one('product.uom', 'Invoicing UoM'),
    }


class project_task(orm.Model):
    _inherit = "project.task"

    _columns = {
        'product_id': fields.many2one('product.product', 'Product'),
        'invoice_line_ids': fields.many2many(
            'account.invoice.line',
            string='Invoice Lines'),
        'invoicing_type': fields.selection([
            ('fixed_amount', 'Fixed Amount'),
            ('time_base', 'Time Base'),
            ], 'Invoicing', required=True),
    }

    _defaults = {
        'invoicing_type': 'time_base',
    }

    def _get_task_product(self, cr, uid, task, context=None):
        product = False
        if task.product_id:
            product = task.product_id
        elif task.typology_id:
            product = task.typology_id.product_id
        return product

    def _get_qty2invoice(self, cr, uid, task, context=None):
        uom_obj = self.pool['product.uom']
        uom_id = task.project_id.invoice_uom_id.id
        qty = uom_obj._compute_qty(
            cr, uid,
            task.project_id.company_uom_id.id,
            task.planned_hours,
            to_uom_id=uom_id)
        return uom_id, qty

    def _get_onchange_product_id_params(self, cr, uid, task, invoice_vals, context=None):
        product = self._get_task_product(cr, uid, task, context=context)
        uom_id, qty = self._get_qty2invoice(cr, uid, task, context=None)
        if not product:
            raise orm.except_orm(
                _('Error'),
                _('The task %s, have no product set. Fix it' % task.name))
        args = [cr, uid, None, product.id, uom_id]
        kwargs = {
            'qty': qty,
            'type': 'out_invoice',
            'partner_id': invoice_vals['partner_id'],
            'fposition_id': invoice_vals['fiscal_position'],
            'context': context,
            'company_id': invoice_vals['company_id'],
        }
        return args, kwargs

    def _prepare_invoice_line_vals(self, cr, uid, task, invoice_vals, context=None):
        invoice_line_obj = self.pool['account.invoice.line']
        args, kwargs = self._get_onchange_product_id_params(
            cr, uid, task, invoice_vals, context=context)
        product_id, uom_id = args[3:4]
        qty = kwargs['qty']
        result = invoice_line_obj.product_id_change(*args, **kwargs)
        vals = result['value']
        vals.update({
            'product_id': product_id,
            'uos_id': uom_id,
            'quantity': qty,
            'invoicing_type': 'fixed_amount',
            'task_ids': [(6, 0, [task.id])],
            'account_analytic_id': task.project_id.analytic_account_id.id,
            })
        return vals

    def _get_onchange_partner_id_params(self, cr, uid, task, context=None):
        args = [cr, uid, None, 'out_invoice', task.project_id.partner_id.id]
        kwargs = {'company_id': task.company_id.id}
        return args, kwargs

    def _prepare_invoice_vals(self, cr, uid, project, grouped_tasks, context=None):
        partner = project.partner_id
        if (not partner) or not (project.pricelist_id):
            raise orm.except_orm(
                _('Analytic Account incomplete'),
                _('Please fill in the Partner or Customer and Sale '
                  'Pricelist fields in the Analytic Account:\n%s')
                % (project.name,))

        args, kwargs = self._get_onchange_partner_id_params(
            cr, uid, task, context=context)
        result = self.onchange_partner_id(*args, **kwargs)
        vals = result['value']
        vals.update({
            'name': time.strftime('%d/%m/%Y') + ' - ' + project.name,
            'partner_id': partner.id,
        })
        lines_vals = []
        for task in grouped_tasks:
            line_vals = self._prepare_invoice_line_vals(
                cr, uid, vals, task, context=context)
            lines_vals.append([0, 0, line_vals])
        invoice_vals['invoice_line'] = lines_vals
        return invoice_vals

    #TODO refactor me in order to support the add line from an
    # existing invoice
    def create_invoice(self, cr, uid, ids, context=None):
        invoice_obj = self.pool.get('account.invoice')
        invoice_ids = []
        project_dict = {}
        for task in self.browse(cr, uid, ids, context=context):
            if not task.invoicing_type == 'fixed_amount':
                raise orm.except_orm(
                    _('Error'),
                    _('The task should not be invoiced that way'))
            if project_dict.get(task.project_id):
                project_dict[task.project_id].append(task)
            else:
                project_dict[task.project_id] = [task]
        for project, grouped_tasks in project_dict.items():
            invoice_vals = self._prepare_invoice_vals(
                cr, uid, project, grouped_tasks, context=context)
            invoice_id = invoice_obj.create(cr, uid, invoice_vals, context=context)
            invoice_ids.append(invoice_id)
            invoice_obj.button_reset_taxes(cr, uid, [invoice_id], context)
        return invoice_ids


class hr_analytic_timesheet(orm.Model):
    _inherit = "hr.analytic.timesheet"

    _columns = {
        'invoice_line_id': fields.many2one(
            'account.invoice.line',
            'Invoice Line'),
    }

    def on_change_account_id(self, cr, uid, ids, account_id, user_id=False, context=None):
        res = super(hr_analytic_timesheet, self).\
            on_change_account_id(cr, uid, ids, account_id, user_id)

        if not res.get('domain'):
            res['domain'] = {}

        project_obj = self.pool.get('project.project')
        project_ids = project_obj.search(cr, uid, [
            ('analytic_account_id', '=', account_id),
            ], context=context)

        res['domain']['task_id'] = [
            ('state', 'not in', ['draft', 'done']),
            ('project_id', 'in', project_ids)
        ]
        return res

    def on_change_task_id(self, cr, uid, ids, account_id, task_id, context=None):
        if task_id:
            task_obj = self.pool.get('project.task')
            fixed_amount_task = task_obj.search(cr, uid, [
                ('invoicing_type', '=', 'time_base'),
                ('id', '=', task_id),
                ], context=context)

            if fixed_amount_task:
                return {'value': {'to_invoice': False}}
        if account_id:
            analytic_obj = self.pool['account.analytic.account']
            analytic = analytic_obj.browse(cr, uid, account_id, context=context)
            return {'value': {'to_invoice': analytic.to_invoice.id}}
        return {}

#Still needed??
#    def on_change_unit_amount(self, cr, uid, sheet_id, prod_id, unit_amount,
#                              company_id, unit=False, journal_id=False,
#                              task_id=False, to_invoice=False, context=None):
#        res = super(HrAnalyticTimesheet, self).on_change_unit_amount(
#            cr, uid, sheet_id, prod_id, unit_amount, company_id, unit,
#            journal_id, task_id, to_invoice, context)
#        if 'value' in res and task_id:
#            task_obj = self.pool.get('project.task')
#            task = task_obj.browse(cr, uid, task_id)
#            if task.fixed_amount:
#                res['value']['to_invoice'] = False
#        return res
#
#    def on_change_user_id(self, cr, uid, ids, user_id, parent_product_id):
#        res = super(HrAnalyticTimesheet, self).on_change_user_id(cr, uid, ids, user_id)
#        if parent_product_id:
#            if not res.get('value'):
#                res['value'] = {}
#            res['value']['product_id'] = parent_product_id
#        return res

    def _get_group_key(self, cr, uid, line, context=None):
        keys = ['product_id.id', 'product_uom_id.id']

        if line.task_id.typology_id and \
                line.task_id.typology_id.is_invoice_group_key:
            keys.append('task_id.typology_id.id')
        else:
            keys.append('task_id.id')
        return keys

    def _build_key(self, cr, uid, line, context=None):
        def getRecAttr(obj, fullKey):
            list_key = fullKey.split('.', 1)
            key = list_key.pop(0)

            if list_key:
                return getRecAttr(obj[key], list_key[0])
            else:
                return obj[key]
        result = ''
        for key in self._get_group_key(cr, uid, line, context=context):
            result += "%s:%s|" % (key, getRecAttr(line, key))
        return result

    def _check_line(self, cr, uid, line, context=None):
        if not line.account_id.partner_id:
            raise orm.except_orm(
                _('Hr Analytic Account incomplete !'),
                _('Please fill in the Partner on the Account:\n%s.')
                % (line.account_id.name,))
        if not line.account_id.pricelist_id:  # still needed?
            raise orm.except_orm(
                _('Hr Analytic Account incomplete !'),
                _('Please fill in the Pricelist on the Account:\n%s.')
                % (line.account_id.name,))
        return True

    def group_lines(self, cr, uid, ids, context=None):
        """ return the line group"""
        result = defaultdict(lambda: defaultdict(list))
        for line in self.browse(cr, uid, ids, context=context):
            self._check_line(cr, uid, line, context=context)
            key = self._build_key(cr, uid, line, context=context)
            result[line.account_id][key].append(line)
        return result

    #TODO FIXME
    #In my case the price is managed on the feature
    #for now I do not know what is the best behaviour without
    #this module so I implement a really simple version for now
    def _get_price(self, cr, uid, line, context=None):
        if line.product_id:
            pricelist = line.task_id.project_id.pricelist_id
            partner_id = line.task_id.project_id.partner_id.id
            price = pricelist.price_get(
                line.product_id.id,
                line.unit_amount or 1.0,
                partner_id,
                context=context)[pricelist.id]
            return price
        raise orm.except_orm(_('USER ERROR'), _('NO PRICE HAVE BEEN FOUND'))

    def _play_onchange_on_line(self, cr, uid, line, invoice, context=None):
        res = self.pool.get('account.invoice.line').product_id_change(
            cr, uid,
            None,
            line.product_id.id,
            line.product_uom_id.id,
            qty=-line.amount,
            type='out_invoice',
            partner_id=invoice.partner_id.id,
            fposition_id=invoice.fiscal_position.id,
            currency_id=invoice.currency_id.id,
            context=context,
            company_id=invoice.company_id.id)
        return res.get('value', [])

    def _get_qty2invoice(self, cr, uid, line, context=None):
        uom_obj = self.pool['product.uom']
        uom_id = line.account_id.invoice_uom_id.id
        qty = uom_obj._compute_qty(
            cr, uid,
            line.account_id.company_uom_id.id,
            line.unit_amount,
            to_uom_id=uom_id)
        return uom_id, qty

    def _prepare_invoice_line_vals(self, cr, uid, line, account, invoice, context=None):
        invoice_line = self._play_onchange_on_line(
            cr, uid, line, invoice, context=context)
        if line.task_id.typology_id and \
                line.task_id.typology_id.is_invoice_group_key:
            name = line.task_id.typology_id.name
        else:
            name = line.task_id.name
        uom_id, qty = self._get_qty2invoice(cr, uid, line, context=context)
        invoice_line.update({
            'price_unit': self._get_price(cr, uid, line, context=context),
            'quantity': qty,
            'discount': False,  # TODO
            'name': name,
            'product_id': line.product_id.id,
            'uos_id': uom_id,
            'account_analytic_id': account.id,
            'task_ids': [[6, 0, [line.task_id.id]]],
            'invoicing_type': 'time_base',
        })
        return invoice_line

    def _update_invoice_line_vals(self, cr, uid, line, invoice_line_vals, context=None):
        uom_id, qty = self._get_qty2invoice(cr, uid, line, context=context)
        invoice_line_vals['quantity'] += qty
        if not line.task_id.id in invoice_line_vals['task_ids'][0][2]:
            invoice_line_vals['task_ids'][0][2].append(line.task_id.id)
        return invoice_line_vals

    def _prepare_invoice_vals(self, cr, uid, account, context=None):
        account_payment_term_obj = self.pool.get('account.payment.term')
        partner = account.partner_id
        date_due = False
        if partner.property_payment_term:
            pterm_list = account_payment_term_obj.compute(
                cr, uid, partner.property_payment_term.id,
                value=1,
                date_ref=time.strftime('%Y-%m-%d'))
            if pterm_list:
                pterm_list = [line[0] for line in pterm_list]
                pterm_list.sort()
                date_due = pterm_list[-1]

        return {
            'partner_id': account.partner_id.id,
            'company_id': account.company_id.id,
            'payment_term': partner.property_payment_term.id or False,
            'account_id': partner.property_account_receivable.id,
            'currency_id': account.pricelist_id.currency_id.id,
            'date_due': date_due,
            'fiscal_position': account.partner_id.property_account_position.id,
            'invoice_line': [],
        }

    def create_invoice(self, cr, uid, ids, data=None, context=None):
        res_partner_obj = self.pool.get('res.partner')
        invoice_line_obj = self.pool.get('account.invoice.line')
        invoice_obj = self.pool.get('account.invoice')
        if context is None:
            context = {}
        invoices_ids = []

        #In case that we have all timesheet line believe to the same partner
        #we give the posibility in the wizard to update an existing invoice
        #instead of creating a new one
        existing_invoice_id = data.get('invoice_id')

        for account, group_lines in self.group_lines(cr, uid, ids, context=context).iteritems():
            if existing_invoice_id:
                invoice_id = existing_invoice_id[0]
            else:
                invoice_vals = self._prepare_invoice_vals(cr, uid, account, context=context)
                ctx = context.copy()
                partner = res_partner_obj.browse(cr, uid, invoice_vals['partner_id'], context)
                ctx['lang'] = partner.lang
                # set company_id in context, so the correct default
                # journal will be selected
                ctx['force_company'] = invoice_vals['company_id']
                # set force_company in context so the correct product
                # properties are selected (eg. income account)
                ctx['company_id'] = invoice_vals['company_id']
                invoice_id = invoice_obj.create(cr, uid, invoice_vals, context=ctx)

            invoice = invoice_obj.browse(cr, uid, invoice_id, context=context)
            invoices_ids.append(invoice_id)
            for key in group_lines:
                line = group_lines[key].pop()
                line_ids = [line.id]
                invoice_line_vals = self._prepare_invoice_line_vals(
                    cr, uid, line, account, invoice, context=context)
                for line in group_lines[key]:
                    invoice_line_vals = self._update_invoice_line_vals(
                        cr, uid, line, invoice_line_vals, context=context)
                    line_ids.append(line.id)
                invoice_line_vals['invoice_id'] = invoice_id
                inv_line_id = invoice_line_obj.create(
                    cr, uid, invoice_line_vals, context=context)
                self.write(cr, uid, line_ids, {
                    'invoice_line_id': inv_line_id,
                    'invoice_id': invoice_id,
                    }, context=context)
        return invoices_ids
