"""Shared decision flow used by every adapter's entrypoint: evaluate, apply any
active pause, audit, respond. Keeping it here means pause handling and audit are
identical across all current and future adapters."""
import time

from . import engine, events, state


def process(adapter, event):
    if adapter.is_config_event(event):
        events.audit(adapter.context(event), "observed", "CFG-001",
                     "configuration changed", event.get("file_path", ""))
        return

    policy = engine.load_policy()
    action = adapter.parse(event)
    decision, rule_id, reason, target = engine.evaluate(policy, action)

    # Time-boxed human pause: downgrade in-scope deny/ask to defer, but LOG it.
    pause = state.active_pause()
    if pause and decision in ("deny", "ask") and state.rule_in_scope(rule_id, pause):
        until = time.strftime("%H:%M:%S", time.localtime(pause["paused_until"]))
        events.audit(adapter.context(event), "paused-bypass", rule_id,
                     f"{reason} [PAUSED until {until}]", target)
        return  # defer: emit no decision, normal permission flow applies

    decision, rule_id, reason = adapter.normalize_decision(decision, rule_id, reason)
    if adapter.AUDIT_ALL or decision != "defer" or rule_id:
        events.audit(adapter.context(event), decision, rule_id, reason, target)
    adapter.respond(decision, rule_id, reason)
