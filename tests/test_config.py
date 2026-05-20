from src.utils.config_loader import load_config


def test_config_loads_all_yaml():
    cfg = load_config()
    assert cfg.keywords.get("themes"), "keywords.yaml must have 'themes'"
    assert cfg.topics.get("topics"), "topics.yaml must have 'topics'"
    assert cfg.profile.get("focus_areas"), "profile.yaml must have 'focus_areas'"
    assert cfg.output.get("output"), "output.yaml must have 'output'"


def test_config_hash_is_stable():
    cfg1 = load_config()
    cfg2 = load_config()
    assert cfg1.config_hash() == cfg2.config_hash()


def test_scoring_weights_sum_close_to_one():
    cfg = load_config()
    weights = cfg.output["scoring"]["weights"]
    total = sum(weights.values())
    assert 0.99 <= total <= 1.01, f"weights should sum ~1.0, got {total}"
