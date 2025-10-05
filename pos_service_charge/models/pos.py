# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models, api, _, tools
from collections import defaultdict
from re import search
from odoo.tools import float_is_zero
import logging

_logger = logging.getLogger(__name__)
from odoo.exceptions import UserError


class ProductServiceCharge(models.Model):
	_inherit = 'product.product'

	is_service_charge = fields.Boolean('Use for service Charge')


class PosConfig(models.Model):
	_inherit = 'pos.config'

	allow_service_charge = fields.Boolean('Allow Service Charge')
	service_charge_amount = fields.Float('Service Charge Amount')
	service_charge_type = fields.Selection([('percentage', 'Percentage'), ('fixed', 'Fixed')],
										   string='Service Charge Type', help='Service Charge Method in POS.')
	product_id = fields.Many2one('product.product', string="Product",
								 domain=[('type', '=', 'service'), ('available_in_pos', '=', True)])
	self_ordering_allow_service_charge = fields.Boolean('Allow Custom Discount')
	self_ordering_service_charge_type = fields.Selection([('percentage', 'Percentage'), ('fixed', 'Fixed')],
										   string='Service Charge Type', help='Service Charge Method in POS.')
	self_ordering_product_id = fields.Many2one('product.product', string="Product",
								 domain=[('type', '=', 'service'), ('available_in_pos', '=', True)])

	self_ordering_service_charge_amount = fields.Float('Service Charge Amount')

	def _get_self_ordering_data(self):
		data = super()._get_self_ordering_data()
		data["config"]["self_ordering_allow_service_charge"] = self.allow_service_charge
		data["config"]["self_ordering_service_charge_type"] = self.service_charge_type
		data["config"]["self_ordering_product_id"] = self.product_id.id
		data["config"]["self_ordering_product_id"] = self.product_id.id
		data["config"]["self_ordering_service_charge_amount"] = self.service_charge_amount
		return data

class ResConfigSettings(models.TransientModel):
	_inherit = 'res.config.settings'

	allow_service_charge = fields.Boolean(related='pos_config_id.allow_service_charge', readonly=False)
	pos_service_charge_amount = fields.Float(related='pos_config_id.service_charge_amount', readonly=False)
	pos_self_ordering_allow_service_charge = fields.Boolean(related='pos_config_id.self_ordering_allow_service_charge', readonly=False)
	service_charge_type = fields.Selection(related='pos_config_id.service_charge_type', readonly=False)
	pos_self_ordering_service_charge_type = fields.Selection(related='pos_config_id.self_ordering_service_charge_type', readonly=False)
	product_id = fields.Many2one(related='pos_config_id.product_id', readonly=False)
	pos_self_ordering_product_id = fields.Many2one(related='pos_config_id.self_ordering_product_id', readonly=False)
	pos_self_ordering_service_charge_amount = fields.Float(related='pos_config_id.self_ordering_service_charge_amount', readonly=False)

class pos_order(models.Model):
	_inherit = 'pos.order'

	service_charge = fields.Float("Service Charge", readonly=True)

	@api.onchange('payment_ids', 'lines')
	def _onchange_amount_all(self):
		for order in self:
			currency = order.pricelist_id.currency_id
			order.amount_paid = sum(payment.amount for payment in order.payment_ids)
			order.amount_return = sum(payment.amount < 0 and payment.amount or 0 for payment in order.payment_ids)
			order.amount_tax = currency.round(
				sum(self._amount_line_tax(line, order.fiscal_position_id) for line in order.lines))
			amount_untaxed = currency.round(sum(line.price_subtotal for line in order.lines))
			order.amount_total = order.amount_tax + amount_untaxed + order.service_charge

	@api.model
	def _order_fields(self, ui_order):
		res = super(pos_order, self)._order_fields(ui_order)
		res['service_charge'] = ui_order.get('service_charge', 0.0)
		return res

	def _export_for_ui(self, order):
		result = super(pos_order, self)._export_for_ui(order)
		result['service_charge'] = order.service_charge
		return result

	def _prepare_service_charge_invoice_line(self):
		return {
			'product_id': self.config_id.product_id.id,
			'quantity': 1,
			'discount': 0,
			'price_unit': self.service_charge,
			'name': self.config_id.product_id.display_name,
			'tax_ids': [(6, 0, [])],
			'product_uom_id': self.config_id.product_id.uom_id.id,
		}

	def _prepare_invoice_vals(self):
		res = super(pos_order, self)._prepare_invoice_vals()
		if self.service_charge > 0:
			sc_line = self._prepare_service_charge_invoice_line()
			inv_lines = res.get('invoice_line_ids')
			inv_lines.append((0, None, sc_line))
			res.update({
				'invoice_line_ids': inv_lines,
			})
		return res


class POSSession(models.Model):
	_inherit = "pos.session"


def _accumulate_amounts(self, data):
	# Accumulate the amounts for each accounting lines group
	# Each dict maps `key` -> `amounts`, where `key` is the group key.
	# E.g. `combine_receivables_bank` is derived from pos.payment records
	# in the self.order_ids with group key of the `payment_method_id`
	# field of the pos.payment record.
	amounts = lambda: {'amount': 0.0, 'amount_converted': 0.0}
	tax_amounts = lambda: {'amount': 0.0, 'amount_converted': 0.0, 'base_amount': 0.0, 'base_amount_converted': 0.0}
	split_receivables_bank = defaultdict(amounts)
	split_receivables_cash = defaultdict(amounts)
	split_receivables_pay_later = defaultdict(amounts)
	combine_receivables_bank = defaultdict(amounts)
	combine_receivables_cash = defaultdict(amounts)
	combine_receivables_pay_later = defaultdict(amounts)
	combine_invoice_receivables = defaultdict(amounts)
	split_invoice_receivables = defaultdict(amounts)
	sales = defaultdict(amounts)
	taxes = defaultdict(tax_amounts)
	stock_expense = defaultdict(amounts)
	stock_return = defaultdict(amounts)
	stock_output = defaultdict(amounts)
	rounding_difference = {'amount': 0.0, 'amount_converted': 0.0}
	# Track the receivable lines of the order's invoice payment moves for reconciliation
	# These receivable lines are reconciled to the corresponding invoice receivable lines
	# of this session's move_id.
	combine_inv_payment_receivable_lines = defaultdict(lambda: self.env['account.move.line'])
	split_inv_payment_receivable_lines = defaultdict(lambda: self.env['account.move.line'])
	rounded_globally = self.company_id.tax_calculation_rounding_method == 'round_globally'
	pos_receivable_account = self.company_id.account_default_pos_receivable_account_id
	currency_rounding = self.currency_id.rounding
	for order in self.order_ids:
		order_is_invoiced = order.is_invoiced
		for payment in order.payment_ids:
			amount = payment.amount
			if float_is_zero(amount, precision_rounding=currency_rounding):
				continue
			date = payment.payment_date
			payment_method = payment.payment_method_id
			is_split_payment = payment.payment_method_id.split_transactions
			payment_type = payment_method.type

			# If not pay_later, we create the receivable vals for both invoiced and uninvoiced orders.
			#   Separate the split and aggregated payments.
			# Moreover, if the order is invoiced, we create the pos receivable vals that will balance the
			# pos receivable lines from the invoice payments.
			if payment_type != 'pay_later':
				if is_split_payment and payment_type == 'cash':
					split_receivables_cash[payment] = self._update_amounts(split_receivables_cash[payment], {'amount': amount},date)
				elif not is_split_payment and payment_type == 'cash':
					combine_receivables_cash[payment_method] = self._update_amounts(combine_receivables_cash[payment_method],{'amount': amount}, date)
				elif is_split_payment and payment_type == 'bank':
					split_receivables_bank[payment] = self._update_amounts(split_receivables_bank[payment], {'amount': amount},date)
				elif not is_split_payment and payment_type == 'bank':
					combine_receivables_bank[payment_method] = self._update_amounts(combine_receivables_bank[payment_method],{'amount': amount}, date)


				# Create the vals to create the pos receivables that will balance the pos receivables from invoice payment moves.
				if order_is_invoiced:
					if is_split_payment:
						split_inv_payment_receivable_lines[payment] |= payment.account_move_id.line_ids.filtered(lambda line: line.account_id == pos_receivable_account)
						split_invoice_receivables[payment] = self._update_amounts(split_invoice_receivables[payment],{'amount': payment.amount}, order.date_order)
					else:
						combine_inv_payment_receivable_lines[payment_method] |= payment.account_move_id.line_ids.filtered(lambda line: line.account_id == pos_receivable_account)
						combine_invoice_receivables[payment_method] = self._update_amounts(combine_invoice_receivables[payment_method],{'amount': payment.amount}, order.date_order)

			# If pay_later, we create the receivable lines.
			#   if split, with partner
			#   Otherwise, it's aggregated (combined)
			# But only do if order is *not* invoiced because no account move is created for pay later invoice payments.
			if payment_type == 'pay_later' and not order_is_invoiced:
				if is_split_payment:
					split_receivables_pay_later[payment] = self._update_amounts(split_receivables_pay_later[payment],{'amount': amount}, date)
				elif not is_split_payment:
					combine_receivables_pay_later[payment_method] = self._update_amounts(combine_receivables_pay_later[payment_method],{'amount': amount}, date)

		if not order_is_invoiced:
			order_taxes = defaultdict(tax_amounts)
			if order.service_charge > 0:
				prod = order.config_id.service_product_id
				service_prod_income_account = prod.with_context(with_company=order.company_id.id).property_account_income_id or prod.categ_id.with_context(with_company=order.company_id.id).property_account_income_categ_id
				if not service_prod_income_account:
					raise UserError(_('Please define income account for this product: "%s" (id:%d).')
									% (prod.name, prod.id))
				sale_key1 = (
					# account
					service_prod_income_account.id,
					# sign
					1,
					# for taxes
					tuple(),
					tuple(),
				)
				sales[sale_key1] = self._update_amounts(sales[sale_key1], {'amount': order.service_charge}, order.date_order)
				sales[sale_key1].setdefault('tax_amount', 0.0)

			for order_line in order.lines:
				line = self._prepare_line(order_line)
				# Combine sales/refund lines
				sale_key = (
					# account
					line['income_account_id'],
					# sign
					-1 if line['amount'] < 0 else 1,
					# for taxes
					tuple((tax['id'], tax['account_id'], tax['tax_repartition_line_id']) for tax in line['taxes']),
					line['base_tags'],
				)
				sales[sale_key] = self._update_amounts(sales[sale_key], {'amount': line['amount']}, line['date_order'])
				sales[sale_key].setdefault('tax_amount', 0.0)
				# Combine tax lines
				for tax in line['taxes']:
					tax_key = (tax['account_id'], tax['tax_repartition_line_id'], tax['id'], tuple(tax['tag_ids']))
					sales[sale_key]['tax_amount'] += tax['amount']
					order_taxes[tax_key] = self._update_amounts(
						order_taxes[tax_key],
						{'amount': tax['amount'], 'base_amount': tax['base']},
						tax['date_order'],
						round=not rounded_globally
					)
				for tax_key, amounts in order_taxes.items():
					if rounded_globally:
						amounts = self._round_amounts(amounts)
				for amount_key, amount in amounts.items():
					taxes[tax_key][amount_key] += amount

				if self.company_id.anglo_saxon_accounting and order.picking_ids.ids:
					# Combine stock lines
					stock_moves = self.env['stock.move'].sudo().search([
						('picking_id', 'in', order.picking_ids.ids),
						('company_id.anglo_saxon_accounting', '=', True),
						('product_id.categ_id.property_valuation', '=', 'real_time')
					])
					for move in stock_moves:
						exp_key = move.product_id._get_product_accounts()['expense']
						out_key = move.product_id.categ_id.property_stock_account_output_categ_id
						amount = -sum(move.sudo().stock_valuation_layer_ids.mapped('value'))
						stock_expense[exp_key] = self._update_amounts(stock_expense[exp_key], {'amount': amount}, move.picking_id.date,
																  force_company_currency=True)
						if move.location_id.usage == 'customer':
							stock_return[out_key] = self._update_amounts(stock_return[out_key], {'amount': amount}, move.picking_id.date,
																		 force_company_currency=True)
						else:
							stock_output[out_key] = self._update_amounts(stock_output[out_key], {'amount': amount}, move.picking_id.date,
																		 force_company_currency=True)

				if self.config_id.cash_rounding:
					diff = order.amount_paid - order.amount_total
				rounding_difference = self._update_amounts(rounding_difference, {'amount': diff}, order.date_order)

				# Increasing current partner's customer_rank
				partners = (order.partner_id | order.partner_id.commercial_partner_id)
				partners._increase_rank('customer_rank')

		if self.company_id.anglo_saxon_accounting:
			global_session_pickings = self.picking_ids.filtered(lambda p: not p.pos_order_id)
			if global_session_pickings:
				stock_moves = self.env['stock.move'].sudo().search([
					('picking_id', 'in', global_session_pickings.ids),
					('company_id.anglo_saxon_accounting', '=', True),
					('product_id.categ_id.property_valuation', '=', 'real_time'),
				])
				for move in stock_moves:
					exp_key = move.product_id._get_product_accounts()['expense']
					out_key = move.product_id.categ_id.property_stock_account_output_categ_id
					amount = -sum(move.stock_valuation_layer_ids.mapped('value'))
					stock_expense[exp_key] = self._update_amounts(stock_expense[exp_key], {'amount': amount}, move.picking_id.date,
															  force_company_currency=True)
					if move.location_id.usage == 'customer':
						stock_return[out_key] = self._update_amounts(stock_return[out_key], {'amount': amount}, move.picking_id.date,
																	 force_company_currency=True)
					else:
						stock_output[out_key] = self._update_amounts(stock_output[out_key], {'amount': amount}, move.picking_id.date,
																	 force_company_currency=True)
		MoveLine = self.env['account.move.line'].with_context(check_move_validity=False)

		data.update({
			'taxes': taxes,
			'sales': sales,
			'stock_expense': stock_expense,
			'split_receivables_bank': split_receivables_bank,
			'combine_receivables_bank': combine_receivables_bank,
			'split_receivables_cash': split_receivables_cash,
			'combine_receivables_cash': combine_receivables_cash,
			'combine_invoice_receivables': combine_invoice_receivables,
			'split_receivables_pay_later': split_receivables_pay_later,
			'combine_receivables_pay_later': combine_receivables_pay_later,
			'stock_return': stock_return,
			'stock_output': stock_output,
			'combine_inv_payment_receivable_lines': combine_inv_payment_receivable_lines,
			'rounding_difference': rounding_difference,
			'MoveLine': MoveLine,
			'split_invoice_receivables': split_invoice_receivables,
			'split_inv_payment_receivable_lines': split_inv_payment_receivable_lines,
		})
		return data
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
