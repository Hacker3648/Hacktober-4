/** @odoo-module */
import { patch } from "@web/core/utils/patch";
import { Order } from "@pos_self_order/app/models/order";
import { OrderWidget } from "@pos_self_order/app/components/order_widget/order_widget";
patch(OrderWidget.prototype, {
    setup() {
        super.setup();
        let order = this.selfOrder.currentOrder
        let service_charge_value = 0;
        let service_val = this.selfOrder.config.self_ordering_service_charge_amount
        if (this.selfOrder.config.self_ordering_service_charge_amount != 0){
            if (this.selfOrder.config.self_ordering_service_charge_type == 'percentage'){

                var subtotal = order.amount_total;
                var service = parseFloat(service_val);
                var percentage_charge = (subtotal * service) /100;
                service_charge_value = percentage_charge;
                order.set_service_charge(service_charge_value)
            }
            if (this.selfOrder.config.self_ordering_service_charge_type == 'fixed'){
                service_charge_value = parseFloat(service_val)
                order.set_service_charge(service_charge_value)
            }
            
            
        }
        // order.amount_total += parseFloat(service_charge_value)
    }
});

patch(Order.prototype, {
    setup(order) {
        super.setup(...arguments);
        this.service_charge = this.get_service_charge() || 0;
    },
    set_service_charge(service_charge){
    	this.service_charge = service_charge;
    },
    get_service_charge(){
    	return this.service_charge;
    },
    



});
