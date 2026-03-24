# 现货 · 期货方案对比（网页版）

基于 [Streamlit](https://streamlit.io) 的购销日历与套保仿真：上传含现货/期货价格的 CSV，在浏览器中完成参数设置、配对盈亏、逐日曲线与（可选）保证金补仓/出金信号图。

## 本文件夹用途

将 **`方案对比网页-GitHub`** 整个目录作为 **独立 Git 仓库根目录** 上传到 GitHub，再部署到 **Streamlit Community Cloud** 即可免费获得公网访问链接（或仅限团队，视 Cloud 设置而定）。

## CSV 格式要求

- 需包含列名（支持 **GBK** 或 **UTF-8**）：
  - **时间**：列名含「时间」或 `Date` / `date`
  - **现货价格**：列名含「现货」
  - **期货价格**：列名含「期货」或「主力」，且含「价格」
- 仓库内提供示例：`sample_prices_template.csv`，可按该表头扩展行数据。

## 本地运行

```bash
cd 方案对比网页-GitHub
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
streamlit run app_scheme_compare.py
```

浏览器打开提示的地址（一般为 `http://localhost:8501`）。

## 上传到 GitHub

1. 在 [GitHub](https://github.com) 新建空仓库（不要勾选自动添加 README，避免推送冲突）。
2. 在本文件夹内执行（将 `YOUR_USER` / `YOUR_REPO` 换成你的）：

```bash
cd 方案对比网页-GitHub
git init
git add .
git commit -m "Initial commit: 现货期货方案对比 Streamlit 应用"
git branch -M main
git remote add origin https://github.com/YOUR_USER/YOUR_REPO.git
git push -u origin main
```

若使用 SSH，把 `remote` 地址改为 `git@github.com:YOUR_USER/YOUR_REPO.git`。

## 部署为公网网页（Streamlit Community Cloud）

1. 打开 [share.streamlit.io](https://share.streamlit.io)，用 GitHub 账号登录。
2. **New app** → 选择刚推送的仓库与分支 `main`。
3. **Main file path** 填：`app_scheme_compare.py`
4. **Deploy**。首次构建约 1～3 分钟。
5. 部署成功后得到 `https://xxx.streamlit.app` 链接，即为网页端入口。

说明：

- `requirements.txt`、`runtime.txt`、`packages.txt` 会被 Cloud 自动识别。
- 若图表中文显示为方框，可保留 `packages.txt` 中的 `fonts-noto-cjk`（已配置）；仍异常时可在应用内以英文环境排查字体。

## 仓库内文件说明

| 文件 / 目录 | 说明 |
|-------------|------|
| `app_scheme_compare.py` | 主程序（Streamlit 入口） |
| `requirements.txt` | Python 依赖 |
| `runtime.txt` | 建议 Python 版本（Cloud） |
| `packages.txt` | 系统字体包（Cloud Debian，可选） |
| `.streamlit/config.toml` | 主题与服务器基础配置 |
| `.gitignore` | 不上传 venv、缓存等 |
| `sample_prices_template.csv` | CSV 列名示例 |

## 许可与隐私

行情数据由用户在网页中 **本地上传**，不写入本仓库；请勿将含敏感业务的 CSV 提交到公开仓库。
