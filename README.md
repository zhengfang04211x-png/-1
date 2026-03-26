# 现货 · 期货方案对比（网页版）

基于 [Streamlit](https://streamlit.io) 的购销日历与套保仿真：上传含现货/期货价格的 CSV，在浏览器中完成参数设置、配对盈亏、逐日曲线与（可选）保证金补仓/出金信号图。

## 本文件夹用途

将 **`方案对比网页-GitHub`** 整个目录作为 **独立 Git 仓库根目录** 上传到 GitHub，再部署到 **Streamlit Community Cloud** 即可免费获得公网访问链接（或仅限团队，视 Cloud 设置而定）。

### 重要：Cloud 报错 `Unable to locate package #` / `Streamlit` 等

**不是「中文依赖」问题。** 若仓库根目录有 **`packages.txt`**，Cloud 会把**每一行**当作 `apt install` 的包名。  
你在文件里写的 **`#` 注释、中文说明、带空格的句子** 会被拆成多个「包名」，就会出现 `Unable to locate package #`、`Streamlit`、`Community` 等错误。

**处理：** 把 `packages.txt` 改成**仅一行** `fonts-noto-cjk`（与仓库模板一致），删掉所有注释和中文说明后推送。若暂时不需要图表中文，可删除整个 `packages.txt`。详见 `部署前必读.txt`。

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

- Cloud 会安装 `requirements.txt`（pip），以及 **`packages.txt`（apt）**。  
- **图表中文**依赖系统字体：本仓库已带 **`packages.txt` 仅一行** `fonts-noto-cjk`，**不要在该文件里写注释或中文**。  
- Python 版本在 **Advanced settings** 里选（建议 **3.11**）。  
- 本仓库为**扁平结构**（根目录仅文件、无子文件夹）；主题等用 Streamlit 默认即可，若需自定义可在本地自行添加 `.streamlit/config.toml`（勿提交 secrets）。

### 若出现 “Error installing requirements”

1. 打开 **Manage app → Logs**，区分 pip 与 apt 报错。  
2. **`packages.txt` 只能有一行** `fonts-noto-cjk`；多行、`#`、中文说明都会导致 apt 失败。  
3. **pip**：`requirements.txt` 保持 `streamlit`、`matplotlib`、`openpyxl`。  
4. 换 Python 版本后 **Reboot app**。

## 仓库内文件说明

| 文件 / 目录 | 说明 |
|-------------|------|
| `app_scheme_compare.py` | 主程序（Streamlit 入口） |
| `requirements.txt` | Python 依赖（含 `pandas`、`numpy`、`streamlit`、`matplotlib`、`openpyxl`） |
| `packages.txt` | **一行** `fonts-noto-cjk`（云端中文字体）；**禁止**注释或中文，否则 apt 失败 |
| `.gitignore` | 不上传 venv、缓存等 |
| `sample_prices_template.csv` | CSV 列名示例 |
| `部署前必读.txt` | 图表中文变方框时的处理 |
| `上传清单.txt` | 推 GitHub / Cloud 前的文件与命令核对 |

## 许可与隐私

行情数据由用户在网页中 **本地上传**，不写入本仓库；请勿将含敏感业务的 CSV 提交到公开仓库。
