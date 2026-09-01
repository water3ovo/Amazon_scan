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
