from pathlib import Path
p = Path(__file__).resolve().parents[1] / "tests/test_utils.py"
s = p.read_text(encoding="utf-8")
s = s.replace('assert "配送>10天" in result', 'assert "配送时间大于10天" in result')
p.write_text(s, encoding="utf-8")
