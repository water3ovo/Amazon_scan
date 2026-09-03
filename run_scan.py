from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.io_excel import create_target_template, load_targets
from src.utils import timestamp_slug

BASE_DIR = Path(__file__).resolve().parent


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Amazon AE/SA 广告前台扫查 V5")
    parser.add_argument("--input", default=str(BASE_DIR / "input" / "scan_targets.xlsx"), help="本地备用扫查输入Excel")
    parser.add_argument("--output", default="", help="输出Excel；留空自动生成时间戳文件")
    parser.add_argument("--headless", action="store_true", help="后台无界面运行（建议先用可见模式验证）")
    parser.add_argument("--no-active-filter", action="store_true", help="不按‘在投状态’过滤本品")
    parser.add_argument("--setup-location", choices=["AE", "SA"], help="首次配置指定国家的配送地址/Profile")
    parser.add_argument("--make-template", action="store_true", help="重新生成 scan_targets.xlsx 示例模板")
    parser.add_argument("--local-only", action="store_true", help="只使用本地 input，不读取/写入 Google Sheet")
    parser.add_argument("--test-google", action="store_true", help="只测试 Google Sheet 连接，不运行扫查")
    return parser


def google_config_path() -> Path:
    return BASE_DIR / "config" / "google_sheets.json"


def build_google_client():
    from src.google_sheets import GoogleSheetsClient
    return GoogleSheetsClient(BASE_DIR, google_config_path())


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

    google_client = None
    use_google = google_config_path().exists() and not args.local_only
    if args.test_google:
        try:
            google_client = build_google_client()
            meta = google_client.test_connection()
            print(f"Google Sheet 连接成功: {meta['title']}")
            print("可见工作表:", ", ".join(meta["sheets"]))
            return 0
        except Exception as exc:
            print(f"[Google Sheet 连接失败] {exc}")
            return 3

    configured_filter = bool(settings.get("scan", {}).get("filter_active_products", True))
    should_filter = configured_filter and not args.no_active_filter

    if use_google:
        try:
            google_client = build_google_client()
            meta = google_client.test_connection()
            print(f"Google Sheet 已连接: {meta['title']}")
            targets = google_client.load_targets(filter_active_products=should_filter)
            print("扫查目标来源: Google Sheet / Mapping")
        except Exception as exc:
            print(f"[错误] Google Sheet Mapping 读取失败: {exc}")
            print("为避免使用过期 Mapping，本次不会自动回退到本地 input。")
            print("如需强制使用本地备用表，请运行: run_scan.py --local-only")
            return 3
    else:
        input_path = Path(args.input)
        targets = load_targets(input_path, filter_active_products=should_filter)
        print(f"扫查目标来源: 本地 {input_path}")

    if not targets:
        print("没有可扫查的ASIN。请检查 Mapping / input、国家/ASIN，以及本品‘在投状态’。")
        return 2

    country_counts = {}
    type_counts = {}
    detail_counts = {}
    for target in targets:
        country_counts[target.country] = country_counts.get(target.country, 0) + 1
        type_counts[target.product_type] = type_counts.get(target.product_type, 0) + 1
        key = f"{target.country}-{target.product_type}"
        detail_counts[key] = detail_counts.get(key, 0) + 1
    print(f"已加载 {len(targets)} 个去重后的 country+ASIN")
    print(f"按国家: {country_counts}")
    print(f"按类型: {type_counts}")
    print(f"明细: {detail_counts}")

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
    print(f"本地备份: {output_path}")

    sync_failed = False
    if google_client is not None:
        try:
            stats = google_client.upsert_results(results)
            own = stats["own"]
            comp = stats["competitor"]
            skipped = stats.get("skipped_failed", 0)
            print("\n=== Google Sheet 写入完成 ===")
            print(f"本品: 新增 {own['inserted']} / 更新 {own['updated']}")
            print(f"竞品: 新增 {comp['inserted']} / 更新 {comp['updated']}")
            if skipped:
                print(f"FAILED 技术失败未写入业务明细: {skipped} 条（本地运行日志仍保留）")
        except Exception as exc:
            sync_failed = True
            print(f"\n[错误] Google Sheet 写入失败: {exc}")
            print(f"本地结果已保留，可稍后重试同步: {output_path}")

    if sync_failed:
        return 3
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n用户中断。")
        raise SystemExit(130)
