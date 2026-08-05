from bank.seed_keywords import SEED_KEYWORDS

VALID_CATEGORIES = {
    "Bills", "Shopping", "Car", "Entertainment", "gifts",
    "Going Out", "Uncategorized", "pet", "food", "rent", "scooter",
}


def test_every_category_name_is_a_real_category():
    # A typo here doesn't fail loudly at runtime — the keyword is just silently
    # skipped and the merchant lands in Uncategorized forever.
    used = {category for _, category in SEED_KEYWORDS}
    assert used <= VALID_CATEGORIES, f"unknown categories: {used - VALID_CATEGORIES}"


def test_no_duplicate_patterns():
    patterns = [pattern for pattern, _ in SEED_KEYWORDS]
    duplicates = {p for p in patterns if patterns.count(p) > 1}
    assert not duplicates, f"duplicate patterns: {duplicates}"


def test_no_pattern_is_too_short():
    short = [p for p, _ in SEED_KEYWORDS if len(p) < 3]
    assert not short, f"patterns under 3 chars will match inside unrelated words: {short}"


def test_patterns_are_normalized():
    bad = [p for p, _ in SEED_KEYWORDS if p != p.strip().lower() or "  " in p]
    assert not bad, f"patterns must be lowercased and single-spaced: {bad}"


def test_substring_patterns_are_ordered_most_specific_first():
    patterns = [pattern for pattern, _ in SEED_KEYWORDS]
    for i, shorter in enumerate(patterns):
        for j, longer in enumerate(patterns):
            if i != j and shorter in longer:
                assert i > j, f"'{longer}' must come before '{shorter}' or it can never match"
