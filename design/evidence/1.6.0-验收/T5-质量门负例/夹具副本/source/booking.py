"""合成评测夹具：会议室预订。只用于核对流程、执行边界与默认配置下的结果，不对应任何真实项目。"""

APPROVAL_REQUIRED_DEFAULT = True  # 默认配置：提交后需要管理员审批
HOLD_MINUTES = 15                 # 开始后超过 15 分钟未签到，由定时任务释放


def submit_booking(user, room, slot, *, find_conflict, save, notify_admin, notify_user,
                   approval_required=APPROVAL_REQUIRED_DEFAULT):
    """一次用户请求：提交预订。"""
    if find_conflict(room, slot):
        return {"status": 409, "error": "时段已被占用"}
    if approval_required:
        booking_id = save(user, room, slot, state="PENDING_APPROVAL")
        notify_admin(booking_id)
        return {"status": 202, "booking_id": booking_id, "state": "PENDING_APPROVAL"}
    booking_id = save(user, room, slot, state="CONFIRMED")
    notify_user(user, booking_id)
    return {"status": 201, "booking_id": booking_id, "state": "CONFIRMED"}


def approve_booking(admin, booking_id, *, load, find_conflict, update, notify_user):
    """另一次请求，由管理员发起：审批待审批的预订。"""
    booking = load(booking_id)
    if booking["state"] != "PENDING_APPROVAL":
        return {"status": 409, "error": "状态不允许审批"}
    if find_conflict(booking["room"], booking["slot"], exclude=booking_id):
        update(booking_id, state="REJECTED")
        return {"status": 409, "error": "审批时发现时段冲突"}
    update(booking_id, state="CONFIRMED")
    notify_user(booking["user"], booking_id)
    return {"status": 200, "state": "CONFIRMED"}


def cancel_booking(user, booking_id, *, load, update):
    """独立触发：用户随时可以取消自己的预订，不是提交之后的必经步骤。"""
    booking = load(booking_id)
    if booking["user"] != user:
        return {"status": 403, "error": "只能取消自己的预订"}
    if booking["state"] not in ("PENDING_APPROVAL", "CONFIRMED"):
        return {"status": 409, "error": "状态不允许取消"}
    update(booking_id, state="CANCELLED")
    return {"status": 200, "state": "CANCELLED"}


def check_in(user, booking_id, *, load, update, now):
    """独立触发：用户到场后签到。"""
    booking = load(booking_id)
    if booking["user"] != user or booking["state"] != "CONFIRMED":
        return {"status": 409, "error": "只有本人的已确认预订可以签到"}
    if now < booking["slot"]["start"]:
        return {"status": 409, "error": "还没到开始时间"}
    update(booking_id, state="CHECKED_IN")
    return {"status": 200, "state": "CHECKED_IN"}


def release_expired(*, list_confirmed_started_before, update, now):
    """定时任务：每分钟运行一次，释放开始超过 HOLD_MINUTES 分钟仍未签到的预订。"""
    released = []
    for booking in list_confirmed_started_before(now - HOLD_MINUTES * 60):
        update(booking["id"], state="RELEASED")
        released.append(booking["id"])
    return released
