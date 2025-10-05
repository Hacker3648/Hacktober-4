/** @odoo-module */

import { PaymentScreenStatus } from "@point_of_sale/app/screens/payment_screen/payment_status/payment_status";
import { patch } from "@web/core/utils/patch";
import { usePos } from "@point_of_sale/app/store/pos_hook";

patch(PaymentScreenStatus.prototype, {
    setup() {
        super.setup();
        this.pos = usePos();
    },
    get service_charges(){
        let order = this.pos.get_order();
        let service_charge    = order ? order.get_service_charge() : 0;
        let total = order ? service_charge + order.get_total_with_tax() : 0;
        return service_charge;
    },

    get subtotal(){
        let order = this.pos.get_order();
        let subtotal = order ? order.get_total_without_tax() : 0;
        return subtotal;
    },

    get total(){
        let order = this.pos.get_order();
        let service_charge    = order ? order.get_service_charge() : 0;
        let total = order ? service_charge + order.get_total_with_tax() : 0;
        return total;
    },

    get taxes(){
        let order = this.pos.get_order();
        var total = order ? order.get_total_with_tax() : 0;
        var taxes = order ? total - order.get_total_without_tax() : 0;
        return taxes;
    }

});
