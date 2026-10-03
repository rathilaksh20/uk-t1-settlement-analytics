"""Data-quality checks. Each check is a SQL query that returns the NUMBER OF
VIOLATIONS (0 means pass). ISIN check digits are validated in Python."""

CHECKS = [
    ("trade_settles_after_trade_date", "critical",
     "SELECT COUNT(*) FROM trades WHERE settlement_date <= trade_datetime::date"),
    ("trade_date_is_business_day", "critical",
     "SELECT COUNT(*) FROM trades t LEFT JOIN business_calendar c ON c.calendar_date = t.trade_datetime::date "
     "WHERE c.calendar_date IS NULL OR NOT c.is_business_day"),
    ("settlement_date_is_business_day", "critical",
     "SELECT COUNT(*) FROM trades t LEFT JOIN business_calendar c ON c.calendar_date = t.settlement_date "
     "WHERE c.calendar_date IS NULL OR NOT c.is_business_day"),
    ("trade_value_equals_qty_times_price", "critical",
     "SELECT COUNT(*) FROM trades WHERE ABS(trade_value - ROUND(quantity * price, 2)) > 0.01"),
    ("every_trade_has_settlement_status", "critical",
     "SELECT COUNT(*) FROM trades t LEFT JOIN settlement_status s USING (trade_id) WHERE s.trade_id IS NULL"),
    ("every_trade_has_four_events", "critical",
     "SELECT COUNT(*) FROM trades t WHERE (SELECT COUNT(*) FROM settlement_events e WHERE e.trade_id = t.trade_id) <> 4"),
    ("event_order_created_confirmed_matched", "critical",
     "SELECT COUNT(*) FROM (SELECT trade_id, "
     "MAX(event_timestamp) FILTER (WHERE event_type = 'TRADE_CREATED')   AS created, "
     "MAX(event_timestamp) FILTER (WHERE event_type = 'TRADE_CONFIRMED') AS confirmed, "
     "MAX(event_timestamp) FILTER (WHERE event_type = 'TRADE_MATCHED')   AS matched, "
     "MAX(event_timestamp) FILTER (WHERE event_type = 'INSTRUCTION_SENT') AS instructed "
     "FROM settlement_events GROUP BY trade_id) x "
     "WHERE created > confirmed OR confirmed > matched OR confirmed > instructed"),
    ("at_risk_iff_flags_exist", "critical",
     "SELECT COUNT(*) FROM settlement_status s WHERE "
     "(s.settlement_status = 'AT_RISK') <> EXISTS (SELECT 1 FROM settlement_flags f WHERE f.trade_id = s.trade_id)"),
    ("primary_reason_matches_status", "critical",
     "SELECT COUNT(*) FROM settlement_status WHERE "
     "(settlement_status = 'READY_TO_SETTLE' AND primary_reason IS NOT NULL) "
     "OR (settlement_status = 'AT_RISK' AND primary_reason IS NULL)"),
    ("buy_needs_cash_sell_needs_securities", "critical",
     "SELECT COUNT(*) FROM trades t JOIN settlement_status s USING (trade_id) WHERE "
     "(t.side = 'BUY'  AND (s.securities_required <> 0 OR ABS(s.cash_required - t.trade_value) > 0.01)) "
     "OR (t.side = 'SELL' AND (s.cash_required <> 0 OR s.securities_required <> t.quantity))"),
    ("flags_and_exceptions_match_one_to_one", "critical",
     "SELECT (SELECT COUNT(*) FROM settlement_flags f LEFT JOIN exceptions e "
     "ON e.trade_id = f.trade_id AND e.exception_type = f.flag_type WHERE e.exception_id IS NULL) "
     "+ (SELECT COUNT(*) FROM exceptions e LEFT JOIN settlement_flags f "
     "ON e.trade_id = f.trade_id AND e.exception_type = f.flag_type WHERE f.trade_id IS NULL)"),
    ("exception_not_resolved_before_created", "critical",
     "SELECT COUNT(*) FROM exceptions WHERE resolved_at < created_at"),
    ("exception_status_consistent_with_resolved_at", "critical",
     "SELECT COUNT(*) FROM exceptions WHERE "
     "(resolution_status = 'OPEN' AND resolved_at IS NOT NULL) "
     "OR (resolution_status = 'RESOLVED' AND resolved_at IS NULL)"),
    ("counterparty_profile_exists_for_traded_counterparties", "warning",
     "SELECT COUNT(DISTINCT t.counterparty_id) FROM trades t "
     "LEFT JOIN counterparty_profile p USING (counterparty_id) WHERE p.counterparty_id IS NULL"),
]


def isin_is_valid(isin):
    if len(isin) != 12 or not isin.isalnum():
        return False
    digits = "".join(str(int(ch, 36)) for ch in isin.upper())
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0