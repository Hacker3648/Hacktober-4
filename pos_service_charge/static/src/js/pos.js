/** @odoo-module */

import { Order, Orderline, Payment } from "@point_of_sale/app/store/models";
import { patch } from "@web/core/utils/patch";
import {
    formatFloat,
    roundDecimals as round_di,
    roundPrecision as round_pr,
    floatIsZero,
} from "@web/core/utils/numbers";

patch(Order.prototype, {
    setup(_defaultObj, options) {
        super.setup(...arguments);
        this.set_service_charge();
    },
    export_as_JSON(){
        const json = super.export_as_JSON(...arguments);
            if (this.pos.config.allow_service_charge){
                var get_service_charge = this.get_service_charge();
                json.service_charge = this.get_service_charge();
                json.amount_total = get_service_charge + this.get_total_with_tax();
            }else{
                json.amount_total = this.get_total_with_tax();
            }
        return json;
    },
    init_from_JSON(json){
        super.init_from_JSON(...arguments);
          if (this.pos.config.allow_service_charge){
            this.service_charge = json.service_charge || 0.0;
          }else{
            this.amount_total = json.amount_total || 0.0;
          }
    },
    set_service_charge(entered_charge){
        this.service_charge = entered_charge;
    },
    get_service_charge(){
        var rounding = this.pos.currency.rounding;
        var percentage_charge = 0;

        var order = this.pos.get_order();
        if (order) {
            if (this.pos.config.service_charge_type === 'fixed') {
                var service = this.service_charge;
                var percentage_charge = service;
                return round_pr(percentage_charge, rounding);
            }
            else if (this.pos.config.service_charge_type === 'percentage') {
                var order = this.pos.get_order();
                var subtotal = order.get_total_without_tax();
                var service = this.service_charge;
                var percentage = (subtotal * service) /100;
                var percentage_charge = percentage;
                return round_pr(percentage_charge, rounding);
            }
            else{
                return 0.0;
            }
        }
    },
    get_change(paymentline){
        if (this.pos.config.allow_service_charge){
            var get_service_charge = this.get_service_charge();
            var rounding = this.pos.currency.rounding;
            if (!paymentline) {
                var change = this.get_total_paid() - (this.get_total_with_tax() + get_service_charge);
            } else {
                var change = -(this.get_total_with_tax() + get_service_charge);
                var lines  = this.paymentlines.models;
                for (var i = 0; i < lines.length; i++) {
                    change += lines[i].get_amount();
                    if (lines[i] === paymentline) {
                        break;
                    }
                }
            }
        }else{
            if (!paymentline) {
				var change =
					this.get_total_paid() - this.get_total_with_tax() - this.get_rounding_applied();
			} else {
				change = -this.get_total_with_tax();
				var lines = this.paymentlines;
				for (var i = 0; i < lines.length; i++) {
					change += lines[i].get_amount();
					if (lines[i] === paymentline) {
						break;
					}
				}
			}
        }
        return round_pr(Math.max(0,change), this.pos.currency.rounding);
    },
    get_due(paymentline){
        if (this.pos.config.allow_service_charge){
            var get_service_charge = this.get_service_charge();
            if (!paymentline) {
                var due = this.get_total_with_tax() - this.get_total_paid() + get_service_charge;
            }
            else {
                var due = this.get_total_with_tax() + this.get_service_charge();
                var lines = this.paymentlines.models;
                for (var i = 0; i < lines.length; i++) {
                    if (lines[i] === paymentline) {
                        break;
                    } else {
                        due -= lines[i].get_amount();
                    }
                }
            }
        }else{
            if (!paymentline) {
				var due =this.get_total_with_tax() - this.get_total_paid() + this.get_rounding_applied();
			} else {
				due = this.get_total_with_tax();
				var lines = this.paymentlines;
				for (var i = 0; i < lines.length; i++) {
					if (lines[i] === paymentline) {
						break;
					} else {
						due -= lines[i].get_amount();
					}
				}
			}
        }
        return round_pr(due, this.pos.currency.rounding);
    },
    getDisplayData() {
        return {
        	...super.getDisplayData(),
            service_charge: this.get_service_charge(),
            total_with_tax : this.get_total_with_tax() + this.get_service_charge(),
        };
    }

});
