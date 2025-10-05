/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { ReceiptScreen } from "@point_of_sale/app/screens/receipt_screen/receipt_screen";
import { usePos } from "@point_of_sale/app/store/pos_hook";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

patch(ReceiptScreen.prototype, {
    setup() {
        super.setup();
        this.pos=usePos();
        this.popup = useService("popup");
        this.orm = useService("orm");
    },
    get total(){
        let order = this.pos.get_order();
        let service_charge    = order ? order.get_service_charge() : 0;
        let total = order ? service_charge + order.get_total_with_tax() : 0;
        return total;
    },

});