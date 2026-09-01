# Amazon Scan V2

Amazon AE / SA 广告前台扫查工具，当前维护版本：**2.0.0-beta.2**。

## 当前职责

`完整 Mapping / 扫查输入 -> 自动筛选本品在投 + 保留竞品 -> 国家+ASIN 去重 -> Amazon 前台扫查 -> 结果 Excel`

- 源码：以本仓库 `main` 分支为唯一维护源。
- 给业务同事使用的 ZIP：放在 Google Drive 发布目录。
- 完整使用说明：见 [`README_使用说明.md`](README_使用说明.md)。

## 数据安全

本仓库当前是 **Public**。请不要提交真实 Mapping、广告/商品业务数据、Chrome Profile、扫描结果、截图、账号信息或任何 Token/凭证。

仓库已忽略：

- `input/*.xlsx` / `input/*.xls`
- `profiles/*`
- `output/*`
- `debug/*`
- `.venv/`

本地 `input/scan_targets.xlsx` 只需粘贴完整 Mapping，程序会自动筛选，不需要人工先整理在投 ASIN。详见 [`input/README.md`](input/README.md)。
