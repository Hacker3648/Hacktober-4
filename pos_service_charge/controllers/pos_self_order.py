# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.

from odoo import http, fields
from odoo.http import request
from odoo.addons.pos_self_order.controllers.orders import PosSelfOrderController
import re
import uuid

class PosSelfOrderControllerInherit(PosSelfOrderController):
	@http.route("/pos-self-order/process-new-order/<device_type>/", auth="public", type="json", website=True)
	def process_new_order(self, order, access_token, table_identifier, device_type):
		lines = order.get('lines')
		is_take_away = order.get('take_away')
		pos_config, table = self._verify_authorization(access_token, table_identifier, is_take_away)
		pos_session = pos_config.current_session_id
		ir_sequence_session = pos_config.env['ir.sequence'].with_context(company_id=pos_config.company_id.id).next_by_code(f'pos.order_{pos_session.id}')

		sequence_number = re.findall(r'\d+', ir_sequence_session)[0]
		order_reference = self._generate_unique_id(pos_session.id, pos_config.id, sequence_number, device_type)

		fiscal_position = (
			pos_config.self_ordering_alternative_fp_id
			if is_take_away
			else pos_config.default_fiscal_position_id
		)

		# Create the order without lines and prices computed
		# We need to remap the order because some required fields are not used in the frontend.
		order = {
			'data': {
				'name': order_reference,
				'sequence_number': sequence_number,
				'uuid': order.get('uuid'),
				'take_away': order.get('take_away'),
				'user_id': request.session.uid,
				'access_token': uuid.uuid4().hex,
				'pos_session_id': pos_session.id,
				'table_id': table.id if table else False,
				'partner_id': False,
				'date_order': str(fields.Datetime.now()),
				'fiscal_position_id': fiscal_position.id,
				'statement_ids': [],
				'lines': [],
				'amount_tax': 0,
				'amount_total': 0,
				'amount_paid': 0,
				'amount_return': 0,
				'table_stand_number': order.get('table_stand_number'),
				'ticket_code': order.get('ticket_code'),
				'service_charge': order.get('service_charge'),
				'pricelist_id': pos_config.pricelist_id.id if pos_config.pricelist_id else False
			},
			'to_invoice': False,
			'session_id': pos_session.id,
		}
		# Save the order in the database to get the id
		posted_order_id = pos_config.env['pos.order'].with_context(from_self=True).create_from_ui([order], draft=True)[0].get('id')

		# Process the lines and get their prices computed
		lines = self._process_lines(lines, pos_config, posted_order_id, is_take_away)

		# Compute the order prices
		amount_total, amount_untaxed = self._get_order_prices(lines)

		# Update the order with the computed prices and lines
		order = pos_config.env["pos.order"].browse(posted_order_id)

		classic_lines = []
		combo_lines = []
		for line in lines:
			if line["combo_parent_uuid"]:
				combo_lines.append(line)
			else:
				classic_lines.append(line)

		# combo lines must be created after classic_line, as they need the classic line identifier
		# use user admin to avoid access rights issues
		lines = pos_config.env['pos.order.line'].with_user(pos_config.self_ordering_default_user_id).create(classic_lines)
		lines += pos_config.env['pos.order.line'].with_user(pos_config.self_ordering_default_user_id).create(combo_lines)

		order.write({
			'lines': lines,
			'state': 'paid' if amount_total == 0 else 'draft',
			'amount_tax': amount_total - amount_untaxed,
			'amount_total': amount_total + order.service_charge,
		})

		order.send_table_count_notification(order.table_id)
		return order._export_for_self_order()



