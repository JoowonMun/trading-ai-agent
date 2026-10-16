"""수집 + 계산 → Context(context.json)."""
import logging
from datetime import date, timedelta

import pandas as pd

from agent.analysis.assessment import assess
from agent.analysis.disclosures import classify
from agent.analysis.financials import build_quarters
from agent.analysis.fundamentals import compute_fundamentals
from agent.analysis.indicators import moving_average, position_in_52w, rsi
from agent.analysis.portfolio import AggregatedPosition, aggregate_positions, summarize, value_positions
from agent.analysis.signals import decide_signal
from agent.analysis.valuation import (band_valuation, choose_method, earnings_points, is_financial,
                                      multiples_from_points)
from agent.collectors.common import NotACompany
from agent.collectors.dart import disclosure_url
from agent.collectors.sec13f import normalize_issuer
from agent.config import Holdings, Settings
from agent.report.schema import (Context, Disclosure, Flows, HoldingContext, IndexQuote, Market, PositionInfo,
                                 PriceSnapshot)

log = logging.getLogger(__name__)

GLOSSARY_TERMS = ["PER", "PBR", "ROE", "영업이익률", "매출 성장률", "영업이익 성장률", "부채비율", "배당수익률",
                  "이동평균선", "RSI", "52주 위치", "PER 밴드", "분할매수", "재검토 기준가", "리밸런싱"]


class ContextError(RuntimeError):
    pass


def price_snapshot(closes: pd.Series) -> PriceSnapshot:
    return PriceSnapshot(
        close=float(closes.iloc[-1]),
        price_date=closes.index[-1].date().isoformat(),
        ma20=moving_average(closes, 20),
        ma60=moving_average(closes, 60),
        ma120=moving_average(closes, 120),
        rsi14=rsi(closes),
        pos_52w_pct=position_in_52w(closes),
    )


def _market(market, today: date) -> Market:
    m = Market()
    try:
        m.fx_usdkrw = market.usdkrw(today)
    except Exception as e:
        m.missing.append(f"환율: {e}")
    try:
        m.indices = {name: IndexQuote(**q) for name, q in market.indices(today).items()}
    except Exception as e:
        m.missing.append(f"지수: {e}")
    return m


def _fetch_closes(market, p: AggregatedPosition, start: date, today: date) -> pd.Series:
    if p.market == "KR":
        return market.kr_closes(p.ticker, start, today)
    return market.us_closes(p.ticker, start, today)


def _analyze_kr(h: HoldingContext, closes: pd.Series, market, dart, settings: Settings, today: date) -> None:
    corp = dart.corp_code(h.ticker)
    company = dart.company(corp)
    quarters = build_quarters(dart.quarterly_reports(corp, years=settings.band_years + 1))
    shares = dart.shares_outstanding(corp)
    if not quarters or not shares:
        raise RuntimeError("재무제표 또는 발행주식수를 찾지 못했습니다")

    points = {m: earnings_points(quarters, m) for m in ("PER", "PBR")}
    _value(h, closes, quarters, points, shares, dart.dividend_per_share(corp),
           is_financial(company.get("induty_code")), settings, decimals=0)

    for row in dart.disclosures(corp, today - timedelta(days=settings.disclosure_days), today):
        category, negative = classify(row["report_nm"])
        d = row["rcept_dt"]
        h.disclosures.append(Disclosure(date=f"{d[:4]}-{d[4:6]}-{d[6:]}", title=row["report_nm"],
                                        category=category, negative=negative,
                                        url=disclosure_url(row["rcept_no"])))

    try:
        flows = market.kr_flows(h.ticker, today)
        h.flows = Flows(**flows) if flows else None
    except Exception as e:
        h.missing.append(f"수급: {e}")

    _signal(h, settings)


def _value(h: HoldingContext, closes: pd.Series, quarters, points, shares, dps, financial: bool,
           settings: Settings, decimals: int) -> None:
    """지표 → 밴드 가격 → 지표 평가 (국내·미국 공통)."""
    close = h.price.close
    h.fundamentals = compute_fundamentals(quarters, close * shares, close, dps)
    h.financial_sector = financial
    method = choose_method(financial, h.fundamentals.ttm_net_income)
    multiples = multiples_from_points(closes.resample("ME").last().dropna(), points[method], shares)
    current = h.fundamentals.per if method == "PER" else h.fundamentals.pbr
    h.valuation = band_valuation(multiples, method, current, close, h.position.avg_price, settings.profile,
                                 settings.band_years, settings.min_band_points, decimals=decimals)
    h.assessments = assess(h.fundamentals, h.valuation, financial)


def _signal(h: HoldingContext, settings: Settings) -> None:
    h.signal, h.signal_reasons = decide_signal(
        h.price.close, h.valuation, h.fundamentals, h.position.weight_pct or 0, settings.profile,
        any(d.negative for d in h.disclosures), h.financial_sector)


def _analyze_us(h: HoldingContext, closes: pd.Series, us, settings: Settings, today: date) -> str | None:
    """분석하고 영문 회사명(13F 매칭용)을 돌려준다."""
    data = us.load(h.ticker, today)
    if not data.quarters or not data.shares:
        raise RuntimeError("재무제표 또는 발행주식수를 찾지 못했습니다")
    _value(h, closes, data.quarters, data.points, data.shares, data.dps, data.financial, settings, decimals=2)
    _signal(h, settings)
    return data.name


def _attach_nps(nps, holdings: list[HoldingContext], dart, market_info: Market, portfolio, settings: Settings) -> tuple[str | None, list[dict]]:
    """국민연금 보유·변동 정보를 붙인다. 실패해도 리포트는 계속된다. 연간 목록 기준일을 돌려준다."""
    annual_as_of, by_name = None, {}
    try:
        annual = nps.annual_holdings()
        annual_as_of = annual.get("as_of")
        by_name = {r["name"]: r for r in annual["rows"]}
    except Exception as e:
        market_info.missing.append(f"국민연금 보유 목록: {e}")

    mine = {h.ticker for h in holdings if h.market == "KR"}
    try:
        portfolio_changes = nps.recent_changes(days=settings.disclosure_days)
    except Exception as e:
        market_info.missing.append(f"국민연금 변동: {e}")
        portfolio_changes = []

    for h in holdings:
        info = {}
        if h.market == "KR":
            try:
                info.update(nps.stake(dart.corp_code(h.ticker)) or {})
            except Exception:
                pass  # ETF 등 DART에 없는 종목, 일시 오류
        if h.name in by_name:
            info.update(annual_rank=by_name[h.name]["rank"], annual_stake_pct=by_name[h.name]["stake_pct"])
        h.nps = info or None

    portfolio.nps_overlap = [h.name for h in holdings if h.name in by_name and by_name[h.name]["rank"] <= 50]
    return annual_as_of, [{**c, "mine": c["ticker"] in mine} for c in portfolio_changes]


def _attach_nps_us(sec, holdings: list[HoldingContext], us_names: dict, market_info: Market) -> dict | None:
    """국민연금 미국 보유(13F)를 붙인다. 내 미국 종목은 영문 회사명으로 매칭한다."""
    try:
        report = sec.report()
    except Exception as e:
        status = getattr(getattr(e, "response", None), "status_code", None)
        log.warning("13F 수집 실패: %s %s", type(e).__name__, status or "")
        market_info.missing.append(f"국민연금 미국 보유: {str(e).splitlines()[0]}")
        return None
    for h in holdings:
        if h.market != "US":
            continue
        key = report.get("tickers", {}).get(h.ticker)
        if key is None and us_names.get(h.ticker):
            key = report.get("names", {}).get(normalize_issuer(us_names[h.ticker]))
        pos = report["positions"].get(key) if key else None
        if pos:
            h.nps = {**(h.nps or {}), "us_rank": pos["rank"], "us_shares": pos["shares"],
                     "us_change_pct": pos["change_pct"], "us_new": pos["new"], "us_period": report["period"]}
    matched = sum(1 for h in holdings if h.nps and h.nps.get("us_rank"))
    log.info("13F %s 기준 %d종목, 내 종목 매칭 %d개", report["period"], len(report["positions"]), matched)
    return {k: v for k, v in report.items() if k not in ("positions", "tickers", "names")}


def build_context(settings: Settings, holdings: Holdings, market, dart, today: date, us=None, nps=None,
                  sec=None) -> Context:
    market_info = _market(market, today)
    log.info("시장 지표 수집 완료")
    positions = aggregate_positions(holdings)
    start = today - timedelta(days=365 * (settings.band_years + 1))

    series: dict[str, pd.Series] = {}
    errors: dict[str, str] = {}
    for p in positions:
        log.info("시세 조회 %s", p.key)
        try:
            series[p.key] = _fetch_closes(market, p, start, today)
        except Exception as e:
            log.warning("시세 실패 %s: %s", p.key, e)
            errors[p.key] = str(e)
    if not series:
        raise ContextError("모든 종목의 시세를 가져오지 못했습니다")

    closes = {key: float(s.iloc[-1]) for key, s in series.items()}
    portfolio = summarize(value_positions(positions, closes, market_info.fx_usdkrw), holdings.cash_krw, settings)

    holding_contexts = []
    us_names: dict[str, str | None] = {}
    for p in positions:
        h = HoldingContext(ticker=p.ticker, name=p.name, market=p.market, asset_class=p.asset_class,
                           position=PositionInfo(qty=p.qty, avg_price=p.avg_price,
                                                 weight_pct=portfolio.weights.get(p.key)))
        holding_contexts.append(h)
        if p.key in errors:
            h.missing.append(f"시세: {errors[p.key]}")
            continue
        h.price = price_snapshot(series[p.key])
        if not p.analyze:
            continue
        log.info("분석 %s", p.key)
        try:
            if p.market == "US":
                if us is None:
                    h.missing.append("미국 재무 데이터 소스가 설정되지 않았습니다")
                    continue
                us_names[h.ticker] = _analyze_us(h, series[p.key], us, settings, today)
            else:
                _analyze_kr(h, series[p.key], market, dart, settings, today)
        except NotACompany:
            h.missing.append("ETF·펀드 등 개별 기업이 아니라 재무 분석 대상이 아닙니다")
        except Exception as e:
            log.warning("분석 실패 %s: %s", p.key, e)
            h.missing.append(f"분석: {e}")

    nps_as_of, nps_changes = (None, [])
    if nps is not None:
        log.info("국민연금 데이터 수집")
        nps_as_of, nps_changes = _attach_nps(nps, holding_contexts, dart, market_info, portfolio, settings)

    nps_us = None
    if sec is not None:
        log.info("국민연금 미국 보유(13F) 수집")
        nps_us = _attach_nps_us(sec, holding_contexts, us_names, market_info)

    return Context(date=today.isoformat(), profile=settings.profile, market=market_info,
                   holdings=holding_contexts, portfolio=portfolio, glossary_terms=GLOSSARY_TERMS,
                   nps_changes=nps_changes, nps_annual_as_of=nps_as_of, nps_us=nps_us)
