"""Context(+Analysis) → 메일 HTML."""
from collections import Counter
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from agent.report.glossary import GLOSSARY, GLOSSARY_SHORT
from agent.report.schema import Analysis, Context, HoldingContext

SIGNAL_LABELS = {"add": "추가매수", "hold": "보유", "trim": "일부매도", "review": "재검토"}
SIGNAL_COLORS = {"add": "#15803d", "hold": "#57534e", "trim": "#b45309", "review": "#b91c1c"}
GRADES = {"good": ("좋음", "#15803d"), "neutral": ("보통", "#78716c"), "caution": ("주의", "#b91c1c")}
FUNDAMENTAL_ROWS = [
    ("PER", "per", "배"), ("PBR", "pbr", "배"), ("ROE", "roe", "%"), ("영업이익률", "op_margin", "%"),
    ("매출 성장률", "rev_yoy", "%"), ("영업이익 성장률", "op_yoy", "%"), ("부채비율", "debt_ratio", "%"),
    ("배당수익률", "div_yield", "%"),
]
DISCLAIMER = ("이 리포트는 공개 데이터를 정해진 공식으로 계산한 개인 참고용 자료이며 투자 권유가 아닙니다. "
              "투자 판단과 그 결과의 책임은 본인에게 있습니다.")


def _num(value, digits=0):
    return "-" if value is None else f"{value:,.{digits}f}"


def _money(value, market="KR"):
    if value is None:
        return "-"
    return f"${value:,.2f}" if market == "US" else f"{value:,.0f}원"


def _signed_pct(value):
    return "-" if value is None else f"{value:+.2f}%"


_env = Environment(loader=FileSystemLoader(Path(__file__).parent / "templates"),
                   autoescape=select_autoescape(["html"]))
_env.filters.update(num=_num, money=_money, signed_pct=_signed_pct)


def price_ladder(h: HoldingContext) -> list[tuple[str, float, bool]]:
    """기준 가격들을 높은 순으로 세우고 그 사이에 현재가를 끼워 넣는다: (이름, 가격, 현재가 여부)."""
    v = h.valuation
    rows = [("일부매도 2차", v.sell[1], False), ("일부매도 1차", v.sell[0], False), ("적정가", v.fair, False),
            ("분할매수 1단계", v.buy[0], False), ("분할매수 2단계", v.buy[1], False),
            ("분할매수 3단계", v.buy[2], False), ("현재가", h.price.close, True)]
    if v.review is not None:
        rows.append(("재검토 기준가", v.review, False))
    return sorted(rows, key=lambda row: -row[1])


def auto_summary(context: Context) -> list[str]:
    if context.report_type == "alert":
        important = sum(1 for a in context.alerts if a.important)
        return [f"알림 {len(context.alerts)}건 (중요 {important}건)"]
    counts = Counter(h.signal for h in context.holdings if h.signal)
    lines = [f"추가매수 후보 {counts['add']}개 · 일부매도 {counts['trim']}개 · "
             f"재검토 {counts['review']}개 · 보유 {counts['hold']}개"]
    if context.portfolio.rebalance:
        lines.append("리밸런싱 제안: " + ", ".join(
            f"{r.label} {r.amount_krw:,.0f}원 {r.action}" for r in context.portfolio.rebalance))
    else:
        lines.append("자산군 비중이 목표 범위 안에 있어요")
    disclosures = [d for h in context.holdings for d in h.disclosures]
    negative = " (악재 유형 포함)" if any(d.negative for d in disclosures) else ""
    lines.append(f"최근 공시 {len(disclosures)}건{negative}")
    return lines


def render_report(context: Context, analysis: Analysis | None, notes: list[str]) -> str:
    if context.report_type == "alert":
        template, title = "alert.html", f"투자 알림 {context.date}"
    else:
        template = "email.html"
        title = f"{'주간 ' if context.weekly else ''}투자 리포트 {context.date}"
    alerts_by_ticker: dict[str, list] = {}
    for a in context.alerts:
        alerts_by_ticker.setdefault(a.ticker, []).append(a)
    return _env.get_template(template).render(
        title=title,
        alerts_by_ticker=alerts_by_ticker,
        holdings_by_ticker={h.ticker: h for h in context.holdings},
        context=context,
        analysis=analysis,
        analyses={h.ticker: h for h in analysis.holdings} if analysis else {},
        summary=analysis.summary if analysis else auto_summary(context),
        notes=notes,
        glossary=GLOSSARY,
        glossary_short=GLOSSARY_SHORT,
        grades=GRADES,
        price_ladder=price_ladder,
        signal_labels=SIGNAL_LABELS,
        signal_colors=SIGNAL_COLORS,
        fundamental_rows=FUNDAMENTAL_ROWS,
        disclaimer=DISCLAIMER,
    )
