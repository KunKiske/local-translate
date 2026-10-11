# 离线词典来源

字典数据来自 [skywind3000/ECDICT](https://github.com/skywind3000/ECDICT)，MIT 许可证全文见 `ECDICT-LICENSE.txt`。释义与词性是原词典内容，界面仅拆分多义项，并将已有词性缩写转为中文；没有标注的词性不会推测补齐。

- 下载日期：2026-10-12
- 固定版本：`bc015ed2e24a7abef49fc6dbbb7fe32c1dadaf8b`
- CSV SHA256：`1a6947e04785db63613a92e14903cdae7954f7e84860b10e68e5c7cbb3f9c3cf`
- 本地索引：768,739 条含中文释义的词条，SQLite / FTS5，约 110 MiB。

运行 `python scripts/build_dictionary.py` 下载并建立索引。原始 CSV 和生成数据库不提交到 Git；打包脚本自动检查数据库，并将数据库及许可证一起打包。用户查询时完全离线。
