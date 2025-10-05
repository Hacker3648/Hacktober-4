/** @odoo-module */

import { Component, onMounted, useRef, useState, useSubEnv } from "@odoo/owl";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { _t } from "@web/core/l10n/translation";
import { usePos } from "@point_of_sale/app/store/pos_hook";
import { ErrorPopup } from "@point_of_sale/app/errors/popups/error_popup";
import { NumberPopup } from "@point_of_sale/app/utils/input_popups/number_popup";
import { useService } from "@web/core/utils/hooks";

export class ServiceChargeButton extends Component {
    static template = "pos_service_charge.ServiceChargeButton";

    setup() {
        super.setup();
        this.pos = usePos();
        this.popup = useService("popup");
    }
    async onClick() {
        let order = this.pos.get_order();
        let self = this;
        if (order.orderlines.length === 0) {
            this.popup.add(ErrorPopup, {
                title: _t('Empty OrderLine'),
                body: _t('Please add product in orderline..'),
            });
        }
        else
        {
            if (this.pos.config.service_charge_type === false) {
                this.popup.add(ErrorPopup, {
                    title: _t('Service Charge Type is not available. '),
                    body: _t('Please select service charge type in pos configuration.'),
                });
            }
            /*if (!this.env.pos.config.product_id) {
                this.showPopup('ErrorPopup', {
                    title: this.env._t('Service Charge Product is not available. '),
                    body: this.env._t('Please select service charge product in pos configuration.'),
                });
            }*/
            else
            {
                const { confirmed, payload: inputNumber } = await this.popup.add(NumberPopup, {
                    startingValue: 0,
                    title: _t('Service Charges'),
                });
                let service_charge = inputNumber !== ""? Math.abs(inputNumber): null;
                if (confirmed && service_charge !== null) {
                    order.set_service_charge(service_charge);
                }
            }
        }
    }
}
ProductScreen.addControlButton({
    component: ServiceChargeButton,
    condition: function() {
        return this.pos.config.service_charge_type;
    },
});
