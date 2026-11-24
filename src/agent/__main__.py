"""CLI: python -m agent {collect,publish,run}."""
import argparse
import json
import logging
import os
import sys
from datetime import date, timedelta
from html import escape
from pathlib import Path

from dotenv import load_dotenv

from agent.analysis.alerts import detect_alerts
from agent.analysis.news import build_news
from agent.analysis.opinions import build_opinion_prompt, check_opinions, drop_news, numbered_news
from agent.analysis.research import pick_research_targets
from agent.analysis.sectors import enrich_us_from_history
from agent.analysis.weekly import decide_report_type, weekly_diff
from agent.collectors.dart import DartClient
from agent.collectors.news import GoogleNews
from agent.collectors.nh import NhClient
from agent.collectors.nps import NpsClient
from agent.collectors.prices import MarketData
from agent.collectors.sectors import SectorData
from agent.collectors.sec13f import Nps13fClient
from agent.collectors.us_fundamentals import YahooFundamentals
from agent.config import Holdings, Settings, combine_holdings, load_holdings, load_settings, today_kst
from agent.delivery.email import send_email
from agent.history.snapshot import make_snapshot
from agent.history.store import SnapshotStore
from agent.report.context import build_context
from agent.report.render import render_report
from agent.report.schema import Alert, Context, MoveReason, NewsReport, Opinions
from agent.report.validate import check_move_reasons, validate_analysis

log = logging.getLogger("agent")


def _day_dir(args) -> Path:
    return args.out / args.date.isoformat()


def _nh_client() -> NhClient:
    return NhClient(os.environ["NH_APP_KEY"], os.environ["NH_APP_SECRET"], cache_dir=Path(".cache/nh"))


def resolve_holdings(settings: Settings, manual: Holdings, notes: list[str], nh_factory=_nh_client) -> Holdings:
    """나무 키가 있으면 나무 잔고를 자동으로 가져와 holdings.yaml의 나무 계좌를 대체한다.

    실패하면 holdings.yaml 그대로 진행하고 리포트에 남긴다.
    """
    if not (os.environ.get("NH_APP_KEY") and os.environ.get("NH_APP_SECRET")):
        return manual
    try:
        synced, cash = nh_factory().holdings(index_tickers=set(settings.index_tickers))
    except Exception as e:
        log.warning("나무 잔고 조회 실패: %s", e)
        if not manual.accounts:
            raise RuntimeError(f"나무 잔고 조회에 실패했고 holdings.yaml에도 보유 종목이 없습니다: {e}") from e
        notes.append(f"나무 잔고 조회 실패 → holdings.yaml 사용 ({type(e).__name__})")
        return manual
    notes.append(f"나무 잔고 자동 조회: {sum(len(a.positions) for a in synced)}종목")
    log.info("나무 잔고 조회 완료")
    return combine_holdings(manual, synced, cash)


def apply_history(context: Context, settings: Settings, store, today: date) -> None:
    """직전 스냅샷과 비교해 알림·메일 종류·주간 비교를 채운다.

    기록을 읽다 생기는 어떤 오류든(저장소 없음, 깨진 파일, 옛 형식) 첫 실행처럼 처리하고 리포트는 계속한다.
    """
    try:
        prev = store.latest_before(today)
        context.alerts = detect_alerts(prev, context, settings)
        context.report_type = decide_report_type(today, prev, context.alerts)
        if context.report_type == "weekly":
            week_prev = store.on_or_before(today - timedelta(days=7)) or prev
            if week_prev is not None:
                start = date.fromisoformat(week_prev["date"]) + timedelta(days=1)
                week_alerts = [Alert(**a) for s in store.between(start, today - timedelta(days=1))
                               for a in s.get("alerts", [])] + context.alerts
                context.weekly = weekly_diff(week_prev, context, week_alerts)
            enrich_us_from_history(context.sectors, store.between(today - timedelta(days=365),
                                                                  today - timedelta(days=1)), today)
        context.research_targets = pick_research_targets(context, settings)
    except Exception as e:
        log.warning("기록 저장소 읽기 실패 — 첫 실행처럼 진행: %s", type(e).__name__)
        context.alerts, context.weekly, context.research_targets = [], None, []
        context.report_type = decide_report_type(today, None, [])
    log.info("메일 종류: %s (알림 %d건)", context.report_type, len(context.alerts))


def collect_news(settings: Settings, context: Context, day: Path, source, today: date) -> None:
    """읽어볼 뉴스를 news.json에 저장한다. 웹에서 온 글이라 해설 AI가 읽는 context.json에는 넣지 않는다."""
    news = build_news(source, context.sectors, settings.news_themes, today)
    (day / "news.json").write_text(news.model_dump_json(indent=2), encoding="utf-8")
    log.info("읽어볼 뉴스 %d건 (누락 %d)", sum(len(g.items) for g in news.groups), len(news.missing))


def cmd_collect(args) -> Path:
    settings = load_settings(args.config_dir / "settings.yaml")
    notes: list[str] = []
    holdings = resolve_holdings(settings, load_holdings(args.config_dir / "holdings.yaml"), notes)
    dart = DartClient(os.environ["DART_API_KEY"], cache_dir=Path(".cache/dart"), today=args.date)
    nps = NpsClient(os.environ["DART_API_KEY"], cache_dir=Path(".cache/dart"), today=args.date)
    sec = Nps13fClient(Path(".cache/dart"))
    sectors = SectorData() if args.date.weekday() == 0 else None  # 업종 온도계는 월요일 주간 리포트에만
    context = build_context(settings, holdings, MarketData(), dart, args.date, us=YahooFundamentals(), nps=nps,
                            sec=sec, sectors=sectors)
    context.notes = notes
    if args.history_dir:
        apply_history(context, settings, SnapshotStore(args.history_dir), args.date)
    day = _day_dir(args)
    day.mkdir(parents=True, exist_ok=True)
    path = day / "context.json"
    path.write_text(context.model_dump_json(indent=2), encoding="utf-8")
    log.info("context 저장: %s", path)
    if sectors is not None:
        collect_news(settings, context, day, GoogleNews(), args.date)
    return path


def cmd_publish(args) -> Path:
    settings = load_settings(args.config_dir / "settings.yaml")
    day = _day_dir(args)
    context = Context.model_validate_json((day / "context.json").read_text(encoding="utf-8"))
    if context.report_type == "none":
        log.info("변화 없음 — 메일 생략")
        return None

    notes, analysis = [], None
    analysis_path = day / "analysis.json"
    if analysis_path.exists():
        analysis, errors = validate_analysis(json.loads(analysis_path.read_text(encoding="utf-8")), context)
        if analysis is not None:
            # 원인 조사는 웹 도구만 가진 별도 AI가 research.json으로 낸다 — 해설 AI가 쓴 move_reasons는 쓰지 않는다
            research_path = day / "research.json"
            research = json.loads(research_path.read_text(encoding="utf-8")) if research_path.exists() else {}
            analysis.move_reasons = {t: MoveReason.model_validate(r) for t, r in research.items()}
        if errors:
            notes.append("AI 분석 검증 실패 → 숫자 리포트로 대체")
            notes.extend(errors[:5])
        elif reason_errors := check_move_reasons(analysis, context):
            analysis.move_reasons = {}   # 원인 조사만 빼고 나머지 해설은 살린다
            notes.append("원인 조사 결과 검증 실패 → 제외")
            notes.extend(reason_errors[:3])
        log.info("AI 해설 상태: %s", f"검증 실패 {len(errors)}건" if errors else "검증 통과")
    else:
        notes.append("AI 분석 없음 → 숫자 리포트")

    news = _load_news(day)
    opinions_path = day / "opinions.json"
    opinions = (Opinions.model_validate_json(opinions_path.read_text(encoding="utf-8"))
                if opinions_path.exists() else None)
    if news and opinions:
        news = drop_news(news, opinions.drop_news)
    html = render_report(context, analysis, notes, news=news, opinions=opinions)
    preview = day / "preview.html"
    preview.write_text(html, encoding="utf-8")
    log.info("미리보기 저장: %s", preview)
    if not args.dry_run:
        subject = (f"[투자 알림] {context.date}" if context.report_type == "alert"
                   else f"{settings.report_subject_prefix} {context.date}")
        send_email(subject, html)
        log.info("메일 발송 완료")
    return preview


def _subject_prefix(args) -> str:
    try:
        return load_settings(args.config_dir / "settings.yaml").report_subject_prefix
    except Exception:
        return "[투자 리포트]"


def cmd_check(args) -> None:
    """AI가 쓴 analysis.json을 검증만 한다 (작성 → check → 수정 반복용)."""
    day = _day_dir(args)
    context = Context.model_validate_json((day / "context.json").read_text(encoding="utf-8"))
    analysis, errors = validate_analysis(json.loads((day / "analysis.json").read_text(encoding="utf-8")), context)
    if analysis is not None:
        errors += check_move_reasons(analysis, context)
    if errors:
        print("검증 실패:")
        for e in errors:
            print(f"- {e}")
        sys.exit(1)
    print("검증 통과")


def cmd_research_prompt(args) -> None:
    """원인 조사 담당 AI(웹 도구만 가진 별도 실행)에게 줄 지시문을 출력한다."""
    context = Context.model_validate_json((_day_dir(args) / "context.json").read_text(encoding="utf-8"))
    guide = Path("prompts/research-guide.md").read_text(encoding="utf-8")
    by_ticker = {h.ticker: h for h in context.holdings}
    weekly = {w.ticker: w for w in (context.weekly.holdings if context.weekly else [])}
    lines = []
    for t in context.research_targets:
        h = by_ticker.get(t)
        moves = [a.message for a in context.alerts if a.ticker == t and a.kind == "big_move"]
        if not moves and t in weekly and weekly[t].return_pct is not None:
            moves = [f"지난주 대비 {weekly[t].return_pct:+.1f}%"]
        market = "미국" if h and h.market == "US" else "국내"
        lines.append(f"- {t} ({h.name if h else t}, {market} 주식): {', '.join(moves)}")
    print(f"{guide}\n\n## 조사할 종목 (기준일 {context.date})\n" + "\n".join(lines))


def cmd_research_save(args) -> None:
    """조사 담당 AI의 답변(JSON)에서 조사 대상 종목의 결과만 골라 research.json으로 저장한다."""
    day = _day_dir(args)
    context = Context.model_validate_json((day / "context.json").read_text(encoding="utf-8"))
    result = json.loads((day / "research_raw.json").read_text(encoding="utf-8")).get("result") or ""
    start, end = result.find("{"), result.rfind("}")
    try:
        raw = json.loads(result[start:end + 1]) if start != -1 else {}
        reasons = {t: MoveReason.model_validate(raw[t]).model_dump() for t in context.research_targets if t in raw}
    except (ValueError, TypeError) as e:
        log.warning("원인 조사 결과 해석 실패: %s", type(e).__name__)
        return
    if reasons:
        (day / "research.json").write_text(json.dumps(reasons, ensure_ascii=False), encoding="utf-8")
    log.info("원인 조사 결과: %d종목", len(reasons))


def _load_news(day: Path) -> NewsReport | None:
    path = day / "news.json"
    return NewsReport.model_validate_json(path.read_text(encoding="utf-8")) if path.exists() else None


def cmd_opinion_prompt(args) -> None:
    """살펴볼 곳 의견 담당 AI(웹 도구만 가진 별도 실행)에게 줄 지시문. 대상이 없으면 아무것도 출력하지 않는다."""
    day = _day_dir(args)
    context = Context.model_validate_json((day / "context.json").read_text(encoding="utf-8"))
    guide = Path("prompts/opinion-guide.md").read_text(encoding="utf-8")
    prompt = build_opinion_prompt(guide, context, _load_news(day))
    if prompt:
        print(prompt)


def cmd_opinion_save(args) -> None:
    """의견 담당 AI의 답변(JSON)을 검증해 통과한 항목만 opinions.json으로 저장한다."""
    day = _day_dir(args)
    context = Context.model_validate_json((day / "context.json").read_text(encoding="utf-8"))
    news = _load_news(day)
    result = json.loads((day / "opinion_raw.json").read_text(encoding="utf-8")).get("result") or ""
    start, end = result.find("{"), result.rfind("}")
    try:
        raw = json.loads(result[start:end + 1]) if start != -1 else {}
    except ValueError as e:
        log.warning("업종 의견 해석 실패: %s", type(e).__name__)
        return
    if not isinstance(raw, dict):
        log.warning("업종 의견 해석 실패: 객체가 아님")
        return
    themes = [g.name for g in (news.groups if news else []) if g.kind == "theme"]
    opinions, errors = check_opinions(raw, context.opinion_sectors, themes, len(numbered_news(news)))
    (day / "opinions.json").write_text(opinions.model_dump_json(indent=2), encoding="utf-8")
    log.info("업종 의견 %d개 · 테마 %d개 (버림 %d) · 뺀 기사 %d건",
             len(opinions.sectors), len(opinions.themes), len(errors), len(opinions.drop_news))


def cmd_save_snapshot(args) -> None:
    """발송이 끝난 뒤 오늘 스냅샷을 기록 저장소 폴더에 쓴다 (커밋·푸시는 워크플로가 한다)."""
    if not args.history_dir:
        raise SystemExit("--history-dir가 필요합니다")
    day = _day_dir(args)
    context = Context.model_validate_json((day / "context.json").read_text(encoding="utf-8"))
    SnapshotStore(args.history_dir).save(make_snapshot(context))
    log.info("스냅샷 저장: %s", context.date)
    opinions = day / "opinions.json"
    if opinions.exists():  # 검증 통과한 AI 의견 — 스냅샷과 따로 둔다 (가설 채점 때 다시 읽는다)
        target = Path(args.history_dir) / "opinions" / f"{context.date}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(opinions.read_text(encoding="utf-8"), encoding="utf-8")
        log.info("업종 의견 기록 저장")


def _notify_on_error(step):
    """예약 실행용. 어떤 오류든 실패 메일을 보내서 '조용히 안 오는' 날이 없게 한다."""
    def wrapped(args):
        try:
            return step(args)
        except Exception as e:
            if not args.dry_run:
                send_email(f"{_subject_prefix(args)} {args.date} 생성 실패",
                           f"<p>오늘 리포트를 만들지 못했습니다: {escape(f'{type(e).__name__}: {e}')}</p>")
            raise
    return wrapped


def cmd_run(args) -> None:
    _notify_on_error(cmd_collect)(args)
    cmd_publish(args)


def main(argv: list[str] | None = None) -> None:
    load_dotenv()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # httpx는 INFO에서 요청 URL 전체를 찍는데, DART는 API 키가 URL 쿼리에 들어간다
    logging.getLogger("httpx").setLevel(logging.WARNING)

    parser = argparse.ArgumentParser(prog="python -m agent")
    parser.add_argument("command", choices=["collect", "check", "publish", "run", "save-snapshot", "research-prompt", "research-save",
                                                 "opinion-prompt", "opinion-save"])
    parser.add_argument("--date", type=date.fromisoformat, default=None, help="기준일 (기본: 오늘, 한국시간)")
    parser.add_argument("--out", type=Path, default=Path("out"))
    parser.add_argument("--config-dir", type=Path, default=Path("config"))
    parser.add_argument("--dry-run", action="store_true", help="메일을 보내지 않고 preview.html만 생성")
    parser.add_argument("--notify-on-error", action="store_true", help="collect·publish 실패 시 실패 알림 메일 발송")
    parser.add_argument("--history-dir", type=Path, default=None,
                        help="기록 저장소 폴더 (주면 직전 스냅샷과 비교해 알림·주간 리포트를 만든다)")
    args = parser.parse_args(argv)
    args.date = args.date or today_kst()

    commands = {"collect": cmd_collect, "check": cmd_check, "publish": cmd_publish, "run": cmd_run,
                "save-snapshot": cmd_save_snapshot, "research-prompt": cmd_research_prompt,
                "research-save": cmd_research_save, "opinion-prompt": cmd_opinion_prompt,
                "opinion-save": cmd_opinion_save}
    step = commands[args.command]
    if args.notify_on_error and args.command in ("collect", "publish"):
        step = _notify_on_error(step)
    step(args)


if __name__ == "__main__":
    main()
