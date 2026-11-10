"""合成评测夹具：只用于核对调用顺序、次数与失败返回。"""


class StockTimeout(Exception):
    pass


class PaymentUnavailable(Exception):
    pass


def create_order(sku, quantity, contact, *, lock_stock, release_stock,
                 pre_charge, save_order, send_sms, sleep, logger):
    try:
        available = lock_stock(sku, quantity)
    except StockTimeout:
        return {"status": 503, "error": "库存检查超时"}
    if not available:
        return {"status": 409, "error": "库存不足"}

    for attempt in range(4):
        try:
            pre_charge(sku, quantity)
            break
        except PaymentUnavailable:
            if attempt == 3:
                release_stock(sku, quantity)
                return {"status": 502, "error": "支付调用失败"}
            sleep(0.2)

    order_id = save_order(sku, quantity, status="pending")
    try:
        send_sms(contact, order_id)
    except Exception:
        logger.warning("短信发送失败")
    return {"status": 201, "order_id": order_id}
