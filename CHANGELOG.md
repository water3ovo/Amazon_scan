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
