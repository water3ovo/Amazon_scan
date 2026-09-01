# 本地输入目录

真实 Mapping / 扫查输入属于业务数据，不提交到 GitHub。

首次使用可运行：

```bat
.venv\Scripts\python.exe run_scan.py --make-template
```

生成 `input/scan_targets.xlsx` 后，把完整 Mapping（含表头）按“值”粘贴进去即可，**不需要手工筛选**：

- 本品：程序自动只保留 `在投状态=在投`。
- 竞品：程序保留全部输入竞品。
- 同一 `国家 + ASIN`：自动去重，只扫一次。

也可使用 `使用指定Excel运行.bat` 直接读取包含 `Mapping` Sheet 的 xlsx。
