def merge_rules_by_field(rules):
    """
    Merge rules that share the same field name.
    - Prefers rule with regex
    - Prefers rule marked required
    - Merges descriptions without duplicates
    """
    merged = {}

    for rule in rules:
        field = rule.get("field", "").strip()

        if not field:
            continue

        if field not in merged:
            merged[field] = {
                "field": field,
                "required": rule.get("required", False),
                "regex": rule.get("regex", ""),
                "description": rule.get("description", "")
            }
        else:
            existing = merged[field]

            # Prefer rule with regex
            if not existing.get("regex") and rule.get("regex"):
                existing["regex"] = rule["regex"]

            # Prefer rule marked required
            if rule.get("required"):
                existing["required"] = True

            # Merge descriptions
            desc1 = existing.get("description", "").strip()
            desc2 = rule.get("description", "").strip()

            if desc2 and desc2 not in desc1:
                if desc1:
                    existing["description"] = f"{desc1}; {desc2}"
                else:
                    existing["description"] = desc2

    return list(merged.values())