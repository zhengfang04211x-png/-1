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

- Cloud 会安装根目录的 `requirements.txt`。默认 **不包含** `packages.txt`，避免 `apt` 阶段偶发失败导致整次构建报错。
- Python 版本在部署页 **Advanced settings** 里选择（建议 **3.11**）。

### 若出现 “Error installing requirements”

1. 打开 **Manage app → Logs**，看报错在 **Installing dependencies**（pip）还是系统包（apt）。  
2. **pip**：确认仓库根目录只有一份依赖文件；可把 `requirements.txt` 保持为当前三行（`streamlit`、`matplotlib`、`openpyxl`）。  
3. 换 **Advanced settings → Python version**（如 3.11）后 **Reboot app**。  
4. 图表中文在网页上显示异常时，再在仓库根目录 **新建** `packages.txt`，内容**仅一行**（不要注释）：`fonts-noto-cjk`，然后重新部署。

## 仓库内文件说明

| 文件 / 目录 | 说明 |
|-------------|------|
| `app_scheme_compare.py` | 主程序（Streamlit 入口） |
| `requirements.txt` | Python 依赖 |
| `packages.txt` | 可选（默认不放）：仅一行 `fonts-noto-cjk` 可改善 Linux 下图表中文；**禁止**写 `#` 注释行，否则 apt 会失败 |
| `.streamlit/config.toml` | 主题与服务器基础配置 |
| `.gitignore` | 不上传 venv、缓存等 |
| `sample_prices_template.csv` | CSV 列名示例 |

## 许可与隐私

行情数据由用户在网页中 **本地上传**，不写入本仓库；请勿将含敏感业务的 CSV 提交到公开仓库。
