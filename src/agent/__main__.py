"""CLI: python -m agent {collect,publish,run}."""
import argparse
import json
import logging
import os
import sys
from datetime import date
from html import escape
from pathlib import Path

from dotenv import load_dotenv

from agent.collectors.dart import DartClient
from agent.collectors.nh import NhClient
from agent.collectors.prices import MarketData
from agent.config import Holdings, Settings, combine_holdings, load_holdings, load_settings, today_kst
from agent.delivery.email import send_email
from agent.report.context import build_context
from agent.report.render import render_report
from agent.report.schema import Context
from agent.report.validate import validate_analysis

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
        notes.append(f"나무 잔고 조회 실패 → holdings.yaml 사용 ({type(e).__name__})")
        return manual
    notes.append(f"나무 잔고 자동 조회: {sum(len(a.positions) for a in synced)}종목")
    return combine_holdings(manual, synced, cash)


def cmd_collect(args) -> Path:
    settings = load_settings(args.config_dir / "settings.yaml")
    notes: list[str] = []
    holdings = resolve_holdings(settings, load_holdings(args.config_dir / "holdings.yaml"), notes)
    dart = DartClient(os.environ["DART_API_KEY"], cache_dir=Path(".cache/dart"), today=args.date)
    context = build_context(settings, holdings, MarketData(), dart, args.date)
    context.notes = notes
    day = _day_dir(args)
    day.mkdir(parents=True, exist_ok=True)
    path = day / "context.json"
    path.write_text(context.model_dump_json(indent=2), encoding="utf-8")
    log.info("context 저장: %s", path)
    return path


def cmd_publish(args) -> Path:
    settings = load_settings(args.config_dir / "settings.yaml")
    day = _day_dir(args)
    context = Context.model_validate_json((day / "context.json").read_text(encoding="utf-8"))

    notes, analysis = [], None
    analysis_path = day / "analysis.json"
    if analysis_path.exists():
        analysis, errors = validate_analysis(json.loads(analysis_path.read_text(encoding="utf-8")), context)
        if errors:
            notes.append("AI 분석 검증 실패 → 숫자 리포트로 대체")
            notes.extend(errors[:5])
    else:
        notes.append("AI 분석 없음 → 숫자 리포트")

    html = render_report(context, analysis, notes)
    preview = day / "preview.html"
    preview.write_text(html, encoding="utf-8")
    log.info("미리보기 저장: %s", preview)
    if not args.dry_run:
        send_email(f"{settings.report_subject_prefix} {context.date}", html)
        log.info("메일 발송 완료")
    return preview


def _subject_prefix(args) -> str:
    try:
        return load_settings(args.config_dir / "settings.yaml").report_subject_prefix
    except Exception:
        return "[투자 리포트]"


def cmd_run(args) -> None:
    """예약 실행용. 어떤 오류든 실패 메일을 보내서 '조용히 안 오는' 날이 없게 한다."""
    try:
        cmd_collect(args)
    except Exception as e:
        if not args.dry_run:
            send_email(f"{_subject_prefix(args)} {args.date} 생성 실패",
                       f"<p>오늘 리포트를 만들지 못했습니다: {escape(f'{type(e).__name__}: {e}')}</p>")
        raise
    cmd_publish(args)


def main(argv: list[str] | None = None) -> None:
    load_dotenv()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # httpx는 INFO에서 요청 URL 전체를 찍는데, DART는 API 키가 URL 쿼리에 들어간다
    logging.getLogger("httpx").setLevel(logging.WARNING)

    parser = argparse.ArgumentParser(prog="python -m agent")
    parser.add_argument("command", choices=["collect", "publish", "run"])
    parser.add_argument("--date", type=date.fromisoformat, default=None, help="기준일 (기본: 오늘, 한국시간)")
    parser.add_argument("--out", type=Path, default=Path("out"))
    parser.add_argument("--config-dir", type=Path, default=Path("config"))
    parser.add_argument("--dry-run", action="store_true", help="메일을 보내지 않고 preview.html만 생성")
    args = parser.parse_args(argv)
    args.date = args.date or today_kst()

    {"collect": cmd_collect, "publish": cmd_publish, "run": cmd_run}[args.command](args)


if __name__ == "__main__":
    main()
