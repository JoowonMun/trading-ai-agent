import importlib.util
from pathlib import Path


def load_sample():
    spec = importlib.util.spec_from_file_location("render_sample", Path("scripts/render_sample.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_readme_sample_analysis_passes_validator():
    from agent.report.validate import validate_analysis
    sample = load_sample()
    _, errors = validate_analysis(sample.SAMPLE_ANALYSIS.model_dump(), sample.sample_context())
    assert errors == []
