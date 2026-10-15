from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from agent.config import load_holdings, load_settings, today_kst


def write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_settings_defaults(tmp_path):
    s = load_settings(write(tmp_path, "s.yaml", "profile:\n  review_drawdown_pct: 15\n"))
    assert s.profile.max_single_weight_pct == 15
    assert s.target_allocation == {"domestic": 30, "us": 40, "index": 30}


def test_allocation_must_sum_to_100(tmp_path):
    with pytest.raises(ValidationError, match="100"):
        load_settings(write(tmp_path, "s.yaml", "target_allocation: {domestic: 50, us: 40, index: 30}\n"))


def test_load_holdings(tmp_path):
    h = load_holdings(write(tmp_path, "h.yaml", """
accounts:
  - name: 나무 국내
    broker: nh
    market: KR
    asset_class: domestic
    positions:
      - { ticker: "005930", name: 삼성전자, qty: 10, avg_price: 71000 }
cash_krw: 1000000
"""))
    assert h.accounts[0].positions[0].ticker == "005930"
    assert h.accounts[0].analyze is True
    assert h.cash_krw == 1_000_000


def test_unquoted_ticker_gives_friendly_error(tmp_path):
    with pytest.raises(ValidationError, match="따옴표"):
        load_holdings(write(tmp_path, "h.yaml", """
accounts:
  - name: a
    broker: nh
    market: KR
    asset_class: domestic
    positions:
      - { ticker: 000660, qty: 1, avg_price: 1 }
"""))


def test_today_kst_from_utc_evening():
    utc_2200 = datetime(2026, 10, 14, 22, 0, tzinfo=timezone.utc)  # = 10/15 07:00 KST
    assert today_kst(utc_2200) == date(2026, 10, 15)


def test_repo_config_files_load():
    from pathlib import Path
    load_settings(Path("config/settings.yaml"))
    load_holdings(Path("config/holdings.example.yaml"))


def test_missing_holdings_file_explains_how_to_create(tmp_path):
    with pytest.raises(FileNotFoundError, match="holdings.example.yaml"):
        load_holdings(tmp_path / "holdings.yaml")


def test_personal_holdings_file_is_git_ignored():
    import subprocess
    result = subprocess.run(["git", "check-ignore", "-q", "config/holdings.yaml"])
    assert result.returncode == 0


def test_combine_holdings_replaces_manual_nh_accounts():
    from agent.config import Account, Holdings, Position, combine_holdings
    manual = Holdings(cash_krw=500, accounts=[
        Account(name="나무 국내(수동)", broker="nh", market="KR", asset_class="domestic",
                positions=[Position(ticker="000001", qty=1, avg_price=1)]),
        Account(name="다른 증권사 계좌", broker="mirae", market="KR", asset_class="index", analyze=False,
                positions=[Position(ticker="360750", qty=1, avg_price=1)]),
    ])
    synced = [Account(name="나무 국내", broker="nh", market="KR", asset_class="domestic",
                      positions=[Position(ticker="005930", qty=2, avg_price=1)])]
    h = combine_holdings(manual, synced, synced_cash=1000)
    assert [a.name for a in h.accounts] == ["나무 국내", "다른 증권사 계좌"]
    assert h.cash_krw == 1500


def test_settings_index_tickers_default_empty():
    from agent.config import Settings
    assert Settings().index_tickers == []
