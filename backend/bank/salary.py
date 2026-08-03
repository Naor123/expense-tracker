def match_salary_rule(conn, counterparty: str) -> bool:
    haystack = (counterparty or "").lower()
    rules = conn.execute("SELECT pattern FROM salary_rules").fetchall()
    return any(rule["pattern"].lower() in haystack for rule in rules)
