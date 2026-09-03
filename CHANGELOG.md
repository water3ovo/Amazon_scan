## 2.0.0-beta.5 - 2026-09-03

- 新增 Google Sheets API 自动读写模式：默认从线上 `Mapping` 直接读取扫查目标，不再要求每天复制本地 input。
- 本品继续只扫描 `在投状态=在投`，竞品全部扫描，并按 `国家+ASIN` 去重。
- 扫查结束后仍保留本地 Excel 原始备份，并自动把结果写回 `本品扫查明细` / `竞品扫查明细`。
- Google Sheet 写回按 `日期+国家+ASIN` upsert：同一天重复运行更新原记录，不新增重复行。
- `FAILED` 技术失败默认不写入业务明细，避免一次网络/浏览器失败覆盖当天已有的成功结果；失败详情仍保留在本地运行日志。
- Google Mapping 读取失败时不会静默回退到旧本地 Mapping，避免误扫过期目标；可使用 `--local-only` 手动启用本地备用输入。
- 新增 `--test-google` 与 `测试GoogleSheet连接.bat`，可在正式扫查前单独验证服务账号密钥和表格权限。
- 新增 `升级V5依赖.bat`，已有 beta4.x 用户只需补装 Google API 依赖，无需重建 `.venv` 或重新配置 AE/SA Profile。
- `config/google_service_account.json` 与 `config/google_sheets.json` 已加入 `.gitignore`，密钥不会进入公开 GitHub。

## 2.0.0-beta.4.2 - 2026-09-02

- 修复本地 `scan_targets.xlsx` 旧模板与 Google Sheet `Mapping` 的 I/J 列顺序不一致：Google Sheet 为 `备注, 在投状态`，旧模板误写为 `在投状态, 备注`。
- 新模板列顺序与 Google Sheet Mapping 完全一致，可直接复制数据。
- 兼容旧模板：若程序检测到 J 列是 `在投/非在投`、I 列并非状态，会自动交换语义，避免本品全部被过滤只剩竞品。
- 输入校验改为识别有效状态值，而不是只判断是否为空。

## 2.0.0-beta.4 - 2026-09-01

- 新增 `购买框状态`：`FOUND` / `NO_BUYBOX` / `PARSE_FAILED`。
- 不再把“没有价格”单独等同于 Buy Box 丢失；改用 Seller、库存、Add to Cart / Buy Now、Amazon 明确不可售文案等多信号判断。
- 第三方抢占会保留实际 Seller 名，例如 `buy box被第三方抢占（Tell Tech Trading FZ-LLC）`。
- 明确无购买框时标记 `buy box丢失`；解析失败只记技术状态 `PARTIAL / purchase_box_parse_failed`，避免误报。
- 本品输出末尾新增 `购买框状态` 列，原有 A:X 列顺序不变。

## 2.0.0-beta.3 - 2026-09-01

- 将业务输出列 `BuyBox卖家` 更名为 `购买框归属`。
- 兼容 AE/SA Buy Box 的 `Shipper / Seller`、`Sold by`、`Delivered by`、`Ships from` 等页面结构。
- 恢复并增强旧版 `merchantInfoFeature_feature_div .offer-display-feature-text-message` 解析逻辑。
- 区分“购买框被第三方占用”和“购买框归属未抓到”：前者标记 `购买框异常`，后者仅作为 `PARTIAL / purchase_box_owner_missing` 技术异常。
- 运行日志新增 `购买框归属` 与 `配送方` 两列，便于排查。

# Changelog

## 2.0.0-beta.2
- 修复 Windows 解压后中文文件名乱码：发布 ZIP 改为标准 UTF-8 文件名标记。
- 批处理文件统一为 Windows CRLF + UTF-8，并在首行切换到 UTF-8 代码页。

## 2.0.0-beta.1 - 2026-09-01
- 重构为 AE/SA 广告扫查专用轻量版。
- 去除内置 Chrome / ChromeDriver。
- 加入 Selenium Manager、独立国家 Profile、配送地址首次配置。
- 输入输出与当前 Google Sheet 扫查结构对齐。
- 本品在投过滤、country+ASIN 去重。
- 技术失败与业务异常拆分。
- 默认仅失败/部分失败截图。
- 删除历史多站点、RAM/容量/屏幕/视频/Bullet Points/图片嵌 Excel 等非当前流程逻辑。
