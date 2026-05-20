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


def test_fixture_hash_present_and_stable():
    cfg1 = load_config()
    cfg2 = load_config()
    fh1 = cfg1.fixture_hash()
    assert fh1, "fixture_hash must be non-empty when fixtures file exists"
    assert len(fh1) == 16, "fixture_hash truncated to 16 hex chars"
    assert fh1 == cfg2.fixture_hash(), "fixture_hash must be deterministic"


def test_profile_has_atom_vocabulary():
    cfg = load_config()
    assert cfg.profile.get("focus_atoms_high"), "profile.yaml must define focus_atoms_high"
    # Spot-check a few essential atoms
    atoms = [a.lower() for a in cfg.profile["focus_atoms_high"]]
    for must_have in ("claude code", "hermes", "grok", "enterprise ai", "hyperscaler"):
        assert must_have in atoms, f"focus_atoms_high missing '{must_have}'"
