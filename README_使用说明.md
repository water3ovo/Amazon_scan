# Amazon AE / SA 广告前台扫查 V2

这是针对当前中东手机/平板广告扫查流程重构的轻量版本。源码包**不再自带 Chrome / ChromeDriver**；使用电脑已有 Chrome，Selenium Manager 自动匹配驱动。

## 1. V2 的业务边界

V2 只负责：

`scan_targets.xlsx -> Amazon 前台 -> scan_results.xlsx`

Mapping、PSI、Portfolio、广告账户“是否在投”等业务关系由 Google Sheet / ChatGPT 侧维护。程序不再把这些规则写死在爬虫里。

如果输入表含“在投状态”列：
- `类型=本品`：默认只扫“在投”行。
- `类型=竞品`：扫描输入的全部竞品。
- 同一国家同一 ASIN 自动去重，只访问一次 Amazon。

## 2. 第一次使用

系统要求：Windows 10/11、Python 3.10+、Google Chrome、可访问 Amazon.ae / Amazon.sa 的网络。

1. 把需要扫查的 ASIN 填入 `input/scan_targets.xlsx`。
2. 双击 `一键安装并运行.bat`。
3. 脚本会创建 `.venv`，安装 Selenium / openpyxl，然后开始扫查。
4. 结果生成在 `output/scan_results_YYYYMMDD_HHMMSS.xlsx`。

以后直接双击 `运行扫查.bat`。

如果你直接从 Google Sheet 下载完整的 `扫查_2026-09.xlsx`，无需手工拆 Mapping：把该 xlsx 拖到 `使用指定Excel运行.bat` 上即可。程序会自动读取 `Mapping` Sheet，并只扫描在投本品 + 输入中的竞品。

## 3. 配送地址（强烈建议首次配置）

V2 为 AE 和 SA 各使用一个独立 Chrome Profile，和你日常 Chrome 的 Profile 分开，因此不会接管你的办公浏览器，也不会使用你的日常 Google/Amazon 登录状态。

首次安装后分别运行：
- `配置配送地址_AE.bat`
- `配置配送地址_SA.bat`

浏览器会打开对应 Amazon 首页。请手动设置实际用于扫查的配送地址，并切到 English。完成后回到命令窗口按 Enter。之后该国家会复用这个独立 Profile。

## 4. 输入格式

推荐列：

`国家 | 类型 | Portfolio/品牌 | 产品 | ASIN | 配置 | 颜色 | URL | 在投状态 | 备注`

程序优先读取名为 `scan_targets` 的 Sheet；如果没有，则会自动读取名为 `Mapping` 的 Sheet。因此当前“扫查_2026-09”导出的 xlsx 也可以直接作为输入。

最少需要：`国家 + ASIN`，URL 可不填，程序会按国家生成标准商品链接。

支持国家：AE / SA。

## 5. 输出结构

结果 Excel 有四个 Sheet：

- `本品扫查明细`：列结构直接匹配当前 Google Sheet 的本品扫查明细。
- `竞品扫查明细`：列结构直接匹配当前 Google Sheet 的竞品扫查明细。
- `运行日志`：技术状态，区分业务异常和抓取失败。
- `运行摘要`：本次扫描数量、失败数、异常数。

技术字段不会混进业务异常：
- `scan_status=OK`：核心字段正常。
- `PARTIAL`：页面能打开，但核心字段部分未解析。
- `FAILED`：验证码、浏览器异常等导致本次没有可靠结果。

## 6. 异常标注

本品当前自动标注：
- 页面异常
- 缺货/不可售
- 库存紧张
- 配送>10天
- BuyBox异常（卖家不包含该国家配置中的 Amazon seller 关键词）

价格涨跌属于“历史对比”，不在单次爬虫里硬判；仍由 Google Sheet 历史结果/ChatGPT 分析层判断。

## 7. 截图策略

V1 每个 ASIN 都截图并嵌入 Excel。V2 默认：
- 正常页面：不截图。
- CAPTCHA / FAILED / PARTIAL：保存截图到 `debug/<国家>/`。
- 业务异常默认不截图，可在 `config/settings.json` 将 `save_screenshot_on_anomaly` 改为 `true`。

## 8. 浏览器与反爬

源码包不自带特殊“防反爬浏览器”。V2 使用真实 Chrome、持久独立 Profile、同一国家复用 Session、同 ASIN 去重、随机访问间隔以及失败退避。遇到 Amazon CAPTCHA 时不会把抓取失败误判成缺货，会记录 `FAILED / amazon_captcha` 并保留调试截图。

不要把访问间隔改得非常低。默认 2~4 秒是可靠性优先配置。

## 9. Headless

默认使用可见浏览器，但不会最大化，也不占用你的日常 Chrome Profile。

命令行后台运行：

```bat
.venv\Scripts\python.exe run_scan.py --headless
```

建议先用可见模式稳定跑几轮，再考虑长期 headless。

## 10. 迁移给别人

把整个 V2 源码文件夹压缩即可，不要包含：

`.venv / profiles / debug / output / __pycache__`

对方安装 Python + Chrome 后运行 `一键安装并运行.bat`。代码不依赖固定 `D:\python` 路径，也不依赖指定 Chrome 版本。

## 11. Chrome 路径特殊情况

正常无需配置。如果公司电脑 Chrome 不在标准路径，可临时设置环境变量 `CHROME_BINARY` 指向 `chrome.exe`，再运行扫查。
