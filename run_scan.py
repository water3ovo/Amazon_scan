from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from src.io_excel import create_target_template, load_targets
from src.utils import timestamp_slug

BASE_DIR = Path(__file__).resolve().parent


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Amazon AE/SA 广告前台扫查 V2")
    parser.add_argument("--input", default=str(BASE_DIR / "input" / "scan_targets.xlsx"), help="扫查输入Excel")
    parser.add_argument("--output", default="", help="输出Excel；留空自动生成时间戳文件")
    parser.add_argument("--headless", action="store_true", help="后台无界面运行（建议先用可见模式验证）")
    parser.add_argument("--no-active-filter", action="store_true", help="不按‘在投状态’过滤本品")
    parser.add_argument("--setup-location", choices=["AE", "SA"], help="首次配置指定国家的配送地址/Profile")
    parser.add_argument("--make-template", action="store_true", help="重新生成 scan_targets.xlsx 示例模板")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    settings = load_json(BASE_DIR / "config" / "settings.json")
    countries = load_json(BASE_DIR / "config" / "countries.json")

    if args.make_template:
        target = BASE_DIR / "input" / "scan_targets.xlsx"
        create_target_template(target)
        print(f"已生成模板: {target}")
        return 0

    if args.setup_location:
        country = args.setup_location
        from src.browser import BrowserSession
        session = BrowserSession(country, settings, countries[country], BASE_DIR, headless=False)
        try:
            session.start()
            session.setup_location()
        finally:
            session.close()
        return 0

    input_path = Path(args.input)
    configured_filter = bool(settings.get("scan", {}).get("filter_active_products", True))
    targets = load_targets(input_path, filter_active_products=configured_filter and not args.no_active_filter)
    if not targets:
        print("没有可扫查的ASIN。请检查输入表、国家/ASIN，以及本品‘在投状态’。")
        return 2

    country_counts = {}
    for target in targets:
        country_counts[target.country] = country_counts.get(target.country, 0) + 1
    print(f"已加载 {len(targets)} 个去重后的 country+ASIN：{country_counts}")

    if args.output:
        output_path = Path(args.output)
    else:
        output_path = BASE_DIR / "output" / f"scan_results_{timestamp_slug()}.xlsx"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    from src.scanner import Scanner
    scanner = Scanner(BASE_DIR, settings, countries, headless=True if args.headless else None)
    results = scanner.run(targets, output_path)

    ok = sum(r.scan_status == "OK" for r in results)
    partial = sum(r.scan_status == "PARTIAL" for r in results)
    failed = sum(r.scan_status == "FAILED" for r in results)
    print("\n=== 扫查完成 ===")
    print(f"OK={ok}, PARTIAL={partial}, FAILED={failed}")
    print(f"结果文件: {output_path}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n用户中断。")
        raise SystemExit(130)
