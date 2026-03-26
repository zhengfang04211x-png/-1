"""
同一套购销日历：方案 A = 不套保（仅现货），方案 B = 套保（现货 + 期货补提金）
用法: streamlit run app_scheme_compare.py
"""
import io
import os
import re
import shutil
import subprocess
from collections import defaultdict
from datetime import date, datetime

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st
import platform


def _linux_noto_cjk_font_files():
    """Debian/Ubuntu/Streamlit Cloud 安装 fonts-noto-cjk 后的常见路径。"""
    roots = [
        "/usr/share/fonts/opentype/noto",
        "/usr/share/fonts/truetype/noto",
        "/usr/share/fonts/opentype/noto-cjk",
    ]
    out = []
    for root in roots:
        if not os.path.isdir(root):
            continue
        try:
            for fn in os.listdir(root):
                lower = fn.lower()
                if not lower.endswith((".ttc", ".ttf", ".otf")):
                    continue
                if "cjk" in lower or "notosans" in lower.replace(" ", ""):
                    out.append(os.path.join(root, fn))
        except OSError:
            continue
    out.sort(key=lambda p: ("bold" in p.lower(), "regular" not in p.lower(), p))
    return out


def _linux_font_family_from_fc_list():
    if not shutil.which("fc-list"):
        return None
    try:
        out = subprocess.check_output(
            ["fc-list", ":lang=zh", "family"],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=10,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, TimeoutError):
        return None
    best = None
    for line in out.splitlines():
        fam = line.split(",")[0].strip()
        if not fam:
            continue
        if any(x in fam for x in ("Noto", "CJK", "Source Han", "WenQuanYi", "文泉驿")):
            return fam
        if best is None:
            best = fam
    return best


def _matplotlib_cjk_fontproperties():
    """Linux 下若已登记 Noto 字体文件，用路径强制绘图中文（图例/轴标签）。"""
    import matplotlib.font_manager as fm

    path = st.session_state.get("_mpl_cjk_font_path")
    if path and os.path.isfile(path):
        return fm.FontProperties(fname=path)
    return None


def _ensure_matplotlib_chinese_font():
    """图表中文：Win/Mac 用系统字体；Linux/云端用 Noto 字体文件注册 + fc-list（需 packages.txt: fonts-noto-cjk）。"""
    plt.rcParams["axes.unicode_minus"] = False
    system = platform.system()
    if system == "Windows":
        st.session_state.pop("_mpl_cjk_font_path", None)
        plt.rcParams["font.family"] = "sans-serif"
        plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial"]
        return
    if system == "Darwin":
        st.session_state.pop("_mpl_cjk_font_path", None)
        plt.rcParams["font.family"] = "sans-serif"
        plt.rcParams["font.sans-serif"] = ["Arial Unicode MS", "PingFang SC", "PingFang HK"]
        return

    # Linux（含 Streamlit Cloud）：按字体文件路径 addfont，避免 .ttc 在 fontManager 里名称对不上
    import matplotlib.font_manager as fm

    st.session_state.pop("_mpl_cjk_font_path", None)
    chosen = None
    fc_paths = []
    if shutil.which("fc-match"):
        for pat in ("Noto Sans CJK SC", "Noto Sans CJK JP", "Noto Sans CJK TC"):
            try:
                out = subprocess.check_output(
                    ["fc-match", "-f", "%{file}", pat],
                    stderr=subprocess.DEVNULL,
                    text=True,
                    timeout=5,
                ).strip()
                if out and os.path.isfile(out) and out not in fc_paths:
                    fc_paths.append(out)
            except (subprocess.CalledProcessError, FileNotFoundError, TimeoutError):
                continue
    _seen_font_path = set()
    for path in fc_paths + _linux_noto_cjk_font_files():
        if path in _seen_font_path:
            continue
        _seen_font_path.add(path)
        try:
            fm.fontManager.addfont(path)
            prop = fm.FontProperties(fname=path)
            chosen = prop.get_name()
            if chosen:
                st.session_state["_mpl_cjk_font_path"] = path
                break
        except Exception:
            continue

    if not chosen:
        try:
            fm._load_fontmanager(try_read_cache=False)
        except Exception:
            pass
        prefer = [
            "Noto Sans CJK SC",
            "Noto Sans CJK TC",
            "Noto Sans CJK JP",
            "Noto Serif CJK SC",
            "Source Han Sans SC",
        ]
        available = {f.name for f in fm.fontManager.ttflist}
        chosen = next((n for n in prefer if n in available), None)
        if chosen is None:
            for n in sorted(available):
                if "Noto" in n and "CJK" in n:
                    chosen = n
                    break

    if not chosen:
        chosen = _linux_font_family_from_fc_list()

    plt.rcParams["font.family"] = "sans-serif"
    if chosen:
        plt.rcParams["font.sans-serif"] = [chosen, "DejaVu Sans", "sans-serif"]
    else:
        plt.rcParams["font.sans-serif"] = ["DejaVu Sans", "sans-serif"]


st.set_page_config(
    page_title="现货与期货配对",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

def _df_rename_cn(df: pd.DataFrame, col_map: dict) -> pd.DataFrame:
    return df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})


# 界面与导出用中文列名（内部计算仍用英文列）
CN_COL_现货逐日 = {
    "Date": "日期",
    "Spot": "现货价",
    "Futures": "期货价",
    "Physical_Inventory": "现货库存吨",
    "Spot_Float_Pnl": "现货持仓浮动盈亏",
    "Spot_Cash": "现货现金",
    "Physical_Realized_Daily": "现货当日已实现盈亏",
    "Daily_Buy_Tons": "当日买入吨",
    "Daily_Sell_Tons": "当日卖出吨",
    "Wealth_Spot_Leg": "现货净资产",
    "Value_Change_Spot": "现货净资产变动",
}

CN_COL_保证金逐日 = {
    **CN_COL_现货逐日,
    "Account_Equity": "期货账户权益",
    "Margin_Required": "占用保证金",
    "Cash_Injection": "当日补充保证金",
    "Cash_Withdrawal": "当日提取出金",
    "Risk_Degree": "风险度",
    "Basis": "基差",
    "Value_Change_Hedged": "含期货与资金流净资产变动",
}


try:
    plt.style.use("seaborn-v0_8-whitegrid")
except OSError:
    try:
        plt.style.use("seaborn-whitegrid")
    except OSError:
        plt.style.use("ggplot")
_ensure_matplotlib_chinese_font()


def extract_futures_variety_name(filename):
    if filename is None:
        return None
    name_without_ext = os.path.splitext(filename)[0]
    matches = re.findall(r"[\u4e00-\u9fa5]+", name_without_ext)
    if matches:
        return max(matches, key=len)
    cleaned = re.sub(r"[0-9_\-\s]+", "", name_without_ext)
    return cleaned or None


def read_price_csv(uploaded_file):
    encoding = "gbk"
    try:
        df = pd.read_csv(uploaded_file, encoding=encoding)
    except Exception:
        encoding = "utf-8-sig"
        df = pd.read_csv(uploaded_file, encoding=encoding)
    df.columns = [str(c).strip() for c in df.columns]
    cols = df.columns
    col_time = next((c for c in cols if "时间" in c or "Date" in c or "date" in c.lower()), None)
    col_spot = next((c for c in cols if "现货" in c), None)
    col_fut = next((c for c in cols if ("期货" in c or "主力" in c) and "价格" in c), None)
    if not (col_time and col_spot and col_fut):
        return None, encoding
    df = df.rename(columns={col_time: "Date", col_spot: "Spot", col_fut: "Futures"})
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    for col in ["Spot", "Futures"]:
        df[col] = pd.to_numeric(df[col].astype(str).str.replace(",", ""), errors="coerce")
    df = df.dropna(subset=["Date", "Spot", "Futures"]).sort_values("Date").reset_index(drop=True)
    df["Date"] = df["Date"].dt.normalize()
    return df, encoding


def _wa_add(inv, avg_cost, qty, unit_cost):
    if qty <= 0:
        return inv, avg_cost
    if inv <= 1e-9:
        return float(qty), float(unit_cost)
    new_inv = inv + qty
    new_avg = (inv * avg_cost + qty * unit_cost) / new_inv
    return float(new_inv), float(new_avg)


def _physical_day(
    by_d,
    d_only,
    spot,
    fut,
    inv,
    avg_cost,
    spot_cash,
    buy_m_def,
    buy_a_def,
    sell_m_def,
    sell_a_def,
    buy_basis="futures",
    buy_fut_mult=1.0,
    buy_fut_add=0.0,
):
    """执行当日购销，返回 (inv, avg_cost, spot_cash, realized_day, buy_qty, sell_qty, capped)。
    买入价：buy_basis=='futures' 时为 当日期货价×buy_fut_mult+buy_fut_add；否则为现货 spot×mult+add。
    卖出价：若事件带 sell_price_on=='futures'，则用 当日期货价×sell_fut_mult+sell_fut_add；否则用现货 spot×mult+add。
    """
    realized_day = 0.0
    buy_qty = sell_qty = 0.0
    capped = False
    for ev in by_d.get(d_only, []):
        bm = ev["mult"] if ev["mult"] is not None else (buy_m_def if ev["kind"] == "buy" else sell_m_def)
        ba = ev["add"] if ev["add"] is not None else (buy_a_def if ev["kind"] == "buy" else sell_a_def)
        t = ev["tons"]
        if ev["kind"] == "buy":
            if buy_basis == "futures":
                px = fut * float(buy_fut_mult) + float(buy_fut_add)
            else:
                px = spot * bm + ba
            inv, avg_cost = _wa_add(inv, avg_cost, t, px)
            spot_cash -= t * px
            buy_qty += t
        else:
            if ev.get("sell_price_on") == "futures":
                try:
                    mf = float(ev.get("sell_fut_mult", 1.0))
                except (TypeError, ValueError):
                    mf = 1.0
                try:
                    af = float(ev.get("sell_fut_add", 0.0))
                except (TypeError, ValueError):
                    af = 0.0
                px = fut * mf + af
            else:
                px = spot * bm + ba
            if ev.get("sell_all"):
                sell_actual = inv if inv > 1e-9 else 0.0
                capped = False
            else:
                sell_actual = min(t, inv) if t > 0 else 0.0
                if t > inv + 1e-9:
                    capped = True
            if sell_actual > 0:
                realized_day += sell_actual * (px - avg_cost)
                spot_cash += sell_actual * px
                inv -= sell_actual
                if inv <= 1e-9:
                    inv = 0.0
                    avg_cost = 0.0
            sell_qty += sell_actual
    return inv, avg_cost, spot_cash, realized_day, buy_qty, sell_qty, capped


def _margin_loop_step(
    i,
    price,
    inv_end,
    ratio,
    m_rate,
    inject_r,
    withdraw_r,
    initial_margin_ratio,
    withdraw_mode,
    withdraw_target_r,
    withdraw_amount,
    current_equity,
    initial_equity_slot,
    withdraw_signal_day,
):
    if initial_equity_slot[0] is None:
        req0 = price * inv_end * ratio * m_rate
        initial_equity_slot[0] = req0 * float(initial_margin_ratio)
        current_equity = initial_equity_slot[0]

    req_margin = price * inv_end * ratio * m_rate
    threshold_lower = req_margin * inject_r
    threshold_upper = req_margin * withdraw_r
    if withdraw_mode == "按倍数出金":
        target_equity = req_margin * withdraw_target_r

    daily_in = daily_out = 0
    wsd = withdraw_signal_day[0]

    if current_equity < threshold_lower:
        injection = threshold_lower - current_equity
        current_equity += injection
        daily_in = injection
        wsd = None
    elif current_equity > threshold_upper:
        if wsd is None:
            wsd = i
        if wsd is not None and i >= wsd + 2 and current_equity > threshold_upper:
            if withdraw_mode == "按倍数出金":
                surplus = current_equity - target_equity
                if surplus > 0:
                    current_equity = target_equity
                    daily_out = surplus
                    wsd = None
            else:
                wdy = (withdraw_amount * 10000) if withdraw_amount else 0
                if wdy > 0 and current_equity - wdy >= threshold_lower:
                    daily_out = wdy
                    current_equity -= daily_out
                    wsd = None
                elif wdy > 0:
                    daily_out = current_equity - threshold_lower
                    if daily_out > 0:
                        current_equity = threshold_lower
                        wsd = None
    else:
        wsd = None

    withdraw_signal_day[0] = wsd
    return current_equity, req_margin, daily_in, daily_out, initial_equity_slot[0]


def simulate_spot_only(price_df, by_d, initial_inventory, pricing):
    """不套保：只做现货库存与购销现金，无期货、无保证金。"""
    buy_m_def, buy_a_def = float(pricing["buy_mult"]), float(pricing["buy_add"])
    sell_m_def, sell_a_def = float(pricing["sell_mult"]), float(pricing["sell_add"])
    buy_basis = pricing.get("buy_basis", "futures")
    buy_fut_mult = float(pricing.get("buy_fut_mult", 1.0))
    buy_fut_add = float(pricing.get("buy_fut_add", 0.0))
    sub = price_df.reset_index(drop=True)
    inv = float(initial_inventory)
    spot0 = float(sub["Spot"].iloc[0])
    avg_cost = spot0 if inv > 1e-9 else 0.0
    spot_cash = 0.0
    warns = []
    capped_days = 0
    inv_l, cash_l, real_l, buy_l, sell_l, avg_l = [], [], [], [], [], []

    for i in range(len(sub)):
        row = sub.iloc[i]
        d_only = pd.Timestamp(row["Date"]).date()
        spot = float(row["Spot"])
        fut = float(row["Futures"])
        inv, avg_cost, spot_cash, realized_day, bq, sq, cap = _physical_day(
            by_d, d_only, spot, fut, inv, avg_cost, spot_cash,
            buy_m_def, buy_a_def, sell_m_def, sell_a_def,
            buy_basis=buy_basis,
            buy_fut_mult=buy_fut_mult,
            buy_fut_add=buy_fut_add,
        )
        if cap:
            capped_days += 1
        inv_l.append(inv)
        cash_l.append(spot_cash)
        real_l.append(realized_day)
        buy_l.append(bq)
        sell_l.append(sq)
        avg_l.append(float(avg_cost))

    out = sub.copy()
    out["Physical_Inventory"] = inv_l
    _inv = out["Physical_Inventory"].to_numpy(dtype=float)
    _spot = out["Spot"].to_numpy(dtype=float)
    _avg = np.asarray(avg_l, dtype=float)
    out["Spot_Float_Pnl"] = np.where(_inv > 1e-9, _inv * (_spot - _avg), 0.0)
    out["Spot_Cash"] = cash_l
    out["Physical_Realized_Daily"] = real_l
    out["Daily_Buy_Tons"] = buy_l
    out["Daily_Sell_Tons"] = sell_l
    out["Wealth_Spot_Leg"] = out["Physical_Inventory"] * out["Spot"] + out["Spot_Cash"]
    base = float(out["Wealth_Spot_Leg"].iloc[0])
    out["Value_Change_Spot"] = out["Wealth_Spot_Leg"] - base
    summary = {
        "delta_spot": float(out["Value_Change_Spot"].iloc[-1]),
        "cum_realized_spot": sum(real_l),
        "final_inventory": inv_l[-1],
        "final_spot_cash": cash_l[-1],
        "ton_days": float(sum(inv_l)),
    }
    if capped_days:
        warns.append(f"有 {capped_days} 个交易日计划卖出量超过当时库存，已按库存截断。")
    return out, summary, warns


def simulate_hedged(price_df, by_d, initial_inventory, pricing, margin_cfg):
    """套保：现货同上 + 期货盈亏 + 补提金。futures_pnl_sign=-1 为做空期货。"""
    pnl_sign = int(margin_cfg.get("futures_pnl_sign", -1))
    ratio = float(margin_cfg["hedge_ratio"])
    m_rate = float(margin_cfg["margin_rate"])
    inject_r = float(margin_cfg["fund_inject_ratio"])
    withdraw_r = float(margin_cfg["fund_withdraw_ratio"])
    withdraw_mode = margin_cfg.get("withdraw_mode", "按倍数出金")
    withdraw_target_r = margin_cfg.get("fund_withdraw_target_ratio", 1.3)
    withdraw_amount = margin_cfg.get("fund_withdraw_amount")
    initial_margin_ratio = float(margin_cfg.get("initial_margin_ratio", 1.3))

    buy_m_def, buy_a_def = float(pricing["buy_mult"]), float(pricing["buy_add"])
    sell_m_def, sell_a_def = float(pricing["sell_mult"]), float(pricing["sell_add"])
    buy_basis = pricing.get("buy_basis", "futures")
    buy_fut_mult = float(pricing.get("buy_fut_mult", 1.0))
    buy_fut_add = float(pricing.get("buy_fut_add", 0.0))

    sub = price_df.reset_index(drop=True)
    inv = float(initial_inventory)
    spot0 = float(sub["Spot"].iloc[0])
    avg_cost = spot0 if inv > 1e-9 else 0.0
    spot_cash = 0.0
    current_equity = None
    initial_equity_slot = [None]
    withdraw_signal_day = [None]
    capped_days = 0

    equity_l, margin_l, inj_l, out_l, risk_l = [], [], [], [], []
    inv_l, cash_l, real_l, buy_l, sell_l = [], [], [], [], []

    for i in range(len(sub)):
        row = sub.iloc[i]
        d_only = pd.Timestamp(row["Date"]).date()
        spot = float(row["Spot"])
        fut = float(row["Futures"])

        if i > 0 and current_equity is not None:
            prev_fut = float(sub["Futures"].iloc[i - 1])
            current_equity += pnl_sign * (fut - prev_fut) * inv * ratio

        inv, avg_cost, spot_cash, realized_day, bq, sq, cap = _physical_day(
            by_d, d_only, spot, fut, inv, avg_cost, spot_cash,
            buy_m_def, buy_a_def, sell_m_def, sell_a_def,
            buy_basis=buy_basis,
            buy_fut_mult=buy_fut_mult,
            buy_fut_add=buy_fut_add,
        )
        if cap:
            capped_days += 1

        inv_end = inv
        ce, req_m, d_in, d_out, _ = _margin_loop_step(
            i,
            fut,
            inv_end,
            ratio,
            m_rate,
            inject_r,
            withdraw_r,
            initial_margin_ratio,
            withdraw_mode,
            withdraw_target_r,
            withdraw_amount,
            current_equity,
            initial_equity_slot,
            withdraw_signal_day,
        )
        current_equity = ce

        equity_l.append(current_equity)
        margin_l.append(req_m)
        inj_l.append(d_in)
        out_l.append(d_out)
        risk_l.append((current_equity / req_m) if req_m > 0 else 0.0)
        inv_l.append(inv_end)
        cash_l.append(spot_cash)
        real_l.append(realized_day)
        buy_l.append(bq)
        sell_l.append(sq)

    out_df = sub.copy()
    out_df["Physical_Inventory"] = inv_l
    out_df["Spot_Cash"] = cash_l
    out_df["Physical_Realized_Daily"] = real_l
    out_df["Daily_Buy_Tons"] = buy_l
    out_df["Daily_Sell_Tons"] = sell_l
    out_df["Account_Equity"] = equity_l
    out_df["Margin_Required"] = margin_l
    out_df["Cash_Injection"] = inj_l
    out_df["Cash_Withdrawal"] = out_l
    out_df["Risk_Degree"] = risk_l
    out_df["Basis"] = out_df["Spot"] - out_df["Futures"]
    out_df["Wealth_Spot_Leg"] = out_df["Physical_Inventory"] * out_df["Spot"] + out_df["Spot_Cash"]

    cum_out = pd.Series(out_l).cumsum()
    cum_in = pd.Series(inj_l).cumsum()
    net_cf = cum_out - cum_in
    base_nh = float(out_df["Wealth_Spot_Leg"].iloc[0])
    init_eq = initial_equity_slot[0] or 0.0
    base_asset = base_nh + init_eq
    out_df["Value_Change_Hedged"] = (
        out_df["Wealth_Spot_Leg"] + out_df["Account_Equity"] + net_cf - base_asset
    )

    summary = {
        "delta_hedged": float(out_df["Value_Change_Hedged"].iloc[-1]),
        "cum_realized_spot": sum(real_l),
        "final_inventory": inv_l[-1],
        "final_spot_cash": cash_l[-1],
        "final_account_equity": equity_l[-1],
        "final_wealth_total": float(
            out_df["Wealth_Spot_Leg"].iloc[-1] + out_df["Account_Equity"].iloc[-1] + net_cf.iloc[-1]
        ),
        "inject_count": sum(1 for x in inj_l if x > 0),
        "withdraw_count": sum(1 for x in out_l if x > 0),
        "ton_days": float(sum(inv_l)),
    }
    warns = []
    if capped_days:
        warns.append(f"有 {capped_days} 个交易日计划卖出量超过当时库存，已按库存截断。")
    return out_df, summary, warns


def _cell_date(cell):
    if cell is None:
        return None
    try:
        if pd.isna(cell):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(cell, datetime):
        return cell.date()
    if isinstance(cell, date):
        return cell
    return pd.Timestamp(cell).date()


def _row_float(r, key, default):
    x = r.get(key)
    if x is None:
        return default
    try:
        if pd.isna(x):
            return default
    except (TypeError, ValueError):
        pass
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def events_from_buy_sell_rows(df_editor, lot_tons):
    """
    每行：购买日按侧栏「现货吨数」、购入价由侧栏选「期货基准」或「CSV 现货」一次性买入；出售日一次性卖出当时全部库存。
    出售价 = 出售日 **CSV 当日期货价** × 表列「出售价期货倍数」+「出售价加价(元/吨)」（可理解为比期货价高卖 1.1 倍或再加固定金额）。
    先买后卖；同日则先买后卖。
    """
    events = []
    if df_editor is None or df_editor.empty:
        return events
    q = float(lot_tons)
    for _, r in df_editor.iterrows():
        pd_buy = _cell_date(r.get("购买日期"))
        pd_sell = _cell_date(r.get("出售日期"))
        if pd_buy is None and pd_sell is None:
            continue
        if pd_buy is not None and q > 0:
            events.append({"kind": "buy", "date": pd_buy, "tons": q, "mult": 1.0, "add": 0.0, "sell_all": False})
        if pd_sell is not None:
            m = _row_float(r, "出售价期货倍数", _DEFAULT_SELL_FUT_MULT)
            a = _row_float(r, "出售价加价(元/吨)", 0.0)
            events.append(
                {
                    "kind": "sell",
                    "date": pd_sell,
                    "tons": 0.0,
                    "mult": 1.0,
                    "add": 0.0,
                    "sell_all": True,
                    "sell_price_on": "futures",
                    "sell_fut_mult": m,
                    "sell_fut_add": a,
                }
            )
    return events


def slice_price_for_events(df, evs):
    ds = [e["date"] for e in evs]
    lo, hi = min(ds), max(ds)
    m = (df["Date"] >= pd.Timestamp(lo)) & (df["Date"] <= pd.Timestamp(hi))
    return df.loc[m].copy().reset_index(drop=True), lo, hi


_COL_ORDER = ("购买日期", "出售日期", "出售价期货倍数", "出售价加价(元/吨)")
_DEFAULT_SELL_FUT_MULT = 1.1


def empty_editor_df():
    return pd.DataFrame(
        {
            "购买日期": pd.to_datetime(["2025-01-02"]),
            "出售日期": pd.to_datetime(["2025-02-05"]),
            "出售价期货倍数": [_DEFAULT_SELL_FUT_MULT],
            "出售价加价(元/吨)": [0.0],
        }
    )


def normalize_ev_sheet(df):
    """将购销表转为 DateColumn 兼容类型（从 session 或旧版字符串列恢复时）。"""
    if df is None:
        return empty_editor_df()
    if not {"购买日期", "出售日期"}.issubset(set(df.columns)):
        return empty_editor_df()
    out = df.copy()
    for col, default in (("出售价期货倍数", _DEFAULT_SELL_FUT_MULT), ("出售价加价(元/吨)", 0.0)):
        if col not in out.columns:
            out[col] = default
    out = out[list(_COL_ORDER)].copy()
    out["购买日期"] = pd.to_datetime(out["购买日期"], errors="coerce")
    out["出售日期"] = pd.to_datetime(out["出售日期"], errors="coerce")
    out["出售价期货倍数"] = pd.to_numeric(out["出售价期货倍数"], errors="coerce").fillna(_DEFAULT_SELL_FUT_MULT)
    out["出售价加价(元/吨)"] = pd.to_numeric(out["出售价加价(元/吨)"], errors="coerce").fillna(0.0)
    return out


_required_editor_cols = {"购买日期", "出售日期"}
if "ev_sheet" not in st.session_state:
    st.session_state.ev_sheet = empty_editor_df()
elif not _required_editor_cols.issubset(set(st.session_state.ev_sheet.columns)):
    st.session_state.ev_sheet = empty_editor_df()
else:
    st.session_state.ev_sheet = normalize_ev_sheet(st.session_state.ev_sheet)

st.title("⚖️ 现货市场 · 期货市场（同等仓位）")
st.caption(
    "**购销**：从 0 吨起算，购买日一次买进、出售日一次卖清，吨数在侧栏「现货吨数」。"
    "**购入价** 默认按 **购买日 CSV 期货价**（可 × 倍数 + 加价），可切换为 **CSV 现货价**。**出售价**：出售日期货 × 表内倍数 + 加价。"
    "**期货**：库存×套保比例；开平配对按 CSV 期货价。库存盯市仍用 CSV 现货列。"
)

with st.sidebar:
    st.header("行情数据")
    uploaded = st.file_uploader("上传 CSV", type=["csv"])
    st.header("期货市场参数")
    hedge_direction = st.radio(
        "期货套保方向",
        ["做空（卖出期货，对冲现货跌价）", "做多（买入期货）"],
        index=0,
        help="持有现货时通常 **做空期货**：期货跌则期货盈利、对冲现货跌价损失。公式：期货账户日盈亏 = 方向 × (今日期货价−昨日价) × 套保吨数。",
    )
    futures_pnl_sign = -1 if hedge_direction.startswith("做空") else 1
    hedge_ratio = st.slider("套保比例", 0.0, 2.0, 1.0, 0.1)
    show_margin_sim = st.checkbox(
        "显示保证金仿真（补仓／出金信号图 + 逐日表）",
        value=False,
        help="开启后按侧栏规则逐日算占用保证金、补充保证金与出金；主区展示**何时补、何时提**的柱状信号图及中文明细表。",
    )
    st.caption("以下参数仅在勾选上一项时参与计算；折叠内为默认值。")
    with st.expander("保证金 / 补提金 / 出金（可选）", expanded=False):
        margin_rate = st.slider("保证金率", 0.05, 0.30, 0.12, 0.01)
        initial_margin_ratio = st.slider(
            "初始保证金倍数",
            1.0,
            2.0,
            1.3,
            0.05,
            help="**首次**建立期货保证金账户时划入的权益 = 当日**占用保证金** × 本倍数（默认 1.3）。"
            "与下方「补金线倍数」不同：后者是每日追保触发线。",
        )
        fund_inject_ratio = st.slider("补金线倍数", 1.0, 2.0, 1.2, 0.1)
        fund_withdraw_ratio = st.slider("提金线倍数", 1.0, 3.0, 1.5, 0.1)
        withdraw_mode = st.radio("出金模式", ["按倍数出金", "按具体金额出金"])
        fund_withdraw_target_ratio = 1.3
        fund_withdraw_amount = None
        if withdraw_mode == "按倍数出金":
            fund_withdraw_target_ratio = st.slider("出金目标倍数", 1.0, 2.0, 1.3, 0.1)
        else:
            fund_withdraw_amount = st.number_input("每次出金（万元）", 0.1, 500.0, 10.0, 0.1)

margin_cfg = {
    "futures_pnl_sign": futures_pnl_sign,
    "hedge_ratio": hedge_ratio,
    "margin_rate": margin_rate,
    "initial_margin_ratio": initial_margin_ratio,
    "fund_inject_ratio": fund_inject_ratio,
    "fund_withdraw_ratio": fund_withdraw_ratio,
    "withdraw_mode": withdraw_mode,
    "fund_withdraw_target_ratio": fund_withdraw_target_ratio,
    "fund_withdraw_amount": fund_withdraw_amount,
}

if not uploaded:
    st.info("请先在左侧上传 CSV。")
    st.stop()

price_df, enc = read_price_csv(uploaded)
if price_df is None:
    st.error("CSV 需包含：日期、现货价格、期货价格列。")
    st.stop()

st.success(f"已读取行情 {len(price_df)} 行（{enc}）")
vn = extract_futures_variety_name(uploaded.name)
if vn:
    st.subheader(f"品种：{vn}")

st.subheader("购销参数（A/B 共用）")
spot_tons = st.number_input(
    "现货吨数 (吨)",
    0.0,
    1e6,
    1.0,
    1.0,
    help="**从 0 吨起算**：到「购买日」一次性买进这么多吨，到「出售日」一次性卖光。典型就是时间段内一买一卖一笔单。",
)
buy_basis_label = st.radio(
    "购入价按什么计价（购买日）",
    ["当日期货价（默认）", "CSV 现货价"],
    index=0,
    horizontal=True,
    help="默认与期货对齐：购入价 = 当日期货收盘价 × 下面倍数 + 加价。选现货则直接用 CSV 里的现货价买入。",
)
buy_basis = "futures" if buy_basis_label.startswith("当日期货") else "spot"
buy_fut_m = 1.0
buy_fut_a = 0.0
if buy_basis == "futures":
    c_b1, c_b2 = st.columns(2)
    with c_b1:
        buy_fut_m = st.number_input(
            "购入×期货(倍)",
            min_value=0.01,
            value=1.0,
            step=0.05,
            help="购入价 = 购买日期货价 × 本项 + 右项",
        )
    with c_b2:
        buy_fut_a = st.number_input(
            "购入+元/吨",
            value=0.0,
            step=10.0,
            help="在「期货价×倍数」上再加减（可负）",
        )
st.info(
    "**售出**：出售日 **期货价 × 表内倍数 + 加价**。**购入**：见上（默认期货基准）；**现货吨数** 为成交量；出售日 **卖光**。"
)

pricing = {
    "buy_basis": buy_basis,
    "buy_fut_mult": float(buy_fut_m),
    "buy_fut_add": float(buy_fut_a),
    "buy_mult": 1.0,
    "buy_add": 0.0,
    "sell_mult": 1.0,
    "sell_add": 0.0,
}

st.markdown("**购销日历**（出售价 = 出售日期货 × 倍数 + 加价）")
_b1, _b2, _b3 = st.columns(3)
with _b1:
    if st.button("删除最后一行", key="ev_drop_last", help="去掉表格最底下一行；至少保留一行。"):
        _cur = normalize_ev_sheet(st.session_state.ev_sheet)
        if len(_cur) > 1:
            st.session_state.ev_sheet = _cur.iloc[:-1].reset_index(drop=True)
        else:
            st.warning("至少保留一行购销记录。")
with _b2:
    if st.button("删除空行", key="ev_drop_empty", help="删掉「购买、出售日期都未填」的行。"):
        _cur = normalize_ev_sheet(st.session_state.ev_sheet)
        _m = _cur["购买日期"].notna() | _cur["出售日期"].notna()
        _filt = _cur.loc[_m].reset_index(drop=True)
        st.session_state.ev_sheet = _filt if not _filt.empty else empty_editor_df()
with _b3:
    if st.button("重置为一笔购销", key="ev_reset_one", help="只保留一行默认日期示例。"):
        st.session_state.ev_sheet = empty_editor_df()
st.caption("表格可点右下角 **+** 加行；多出来的行若不好删，可用上方「删除最后一行」或「删除空行」。")
df_e = st.data_editor(
    normalize_ev_sheet(st.session_state.ev_sheet),
    num_rows="dynamic",
    column_config={
        "购买日期": st.column_config.DateColumn(
            "购买日期",
            required=False,
            format="YYYY-MM-DD",
        ),
        "出售日期": st.column_config.DateColumn(
            "出售日期",
            required=False,
            format="YYYY-MM-DD",
        ),
        "出售价期货倍数": st.column_config.NumberColumn(
            "出售价×期货(倍)",
            help="实际出售价 = 出售日 CSV 期货收盘价 × 本列 + 右列加价",
            min_value=0.01,
            step=0.05,
            format="%.4g",
        ),
        "出售价加价(元/吨)": st.column_config.NumberColumn(
            "出售价+元/吨",
            help="在「期货价×倍数」基础上再加减的金额（可填负数）",
            step=10.0,
            format="%.2f",
        ),
    },
    hide_index=True,
    key="editor_main",
    use_container_width=True,
)
st.session_state.ev_sheet = df_e.copy()

run = st.button("运行对比", type="primary")
if not run:
    st.caption("填好购销表后点击「运行对比」。")
    st.stop()

if spot_tons <= 0:
    st.error("「现货吨数」须大于 0。")
    st.stop()

events = events_from_buy_sell_rows(df_e, spot_tons)
if not events:
    st.warning("请在表格中至少填写一个「购买日期」或「出售日期」。")
    st.stop()

for _, r in df_e.iterrows():
    db = _cell_date(r.get("购买日期"))
    ds = _cell_date(r.get("出售日期"))
    if db is not None and ds is not None and ds < db:
        st.warning("存在「出售日期早于购买日期」的行；若当日无库存，卖出量为 0。")
        break


def build_by_d(evs):
    by_d = defaultdict(list)
    for i, e in enumerate(evs):
        by_d[e["date"]].append((i, e))
    for d0 in by_d:
        by_d[d0] = [x[1] for x in sorted(by_d[d0], key=lambda x: x[0])]
    return by_d


def lookup_spot_fut(df, d):
    if d is None:
        return None, None
    ts = pd.Timestamp(d).normalize()
    hit = df[df["Date"].dt.normalize() == ts]
    if hit.empty:
        return None, None
    row = hit.iloc[0]
    return float(row["Spot"]), float(row["Futures"])


def futures_mtm_cumulative_wan(sub, df_editor, lot_tons, hedge_ratio, pnl_sign):
    """
    期货套保：每笔按「购买日期货价开仓、出售日期货价平仓」计。
    逐日累计 = 各笔已平仓的已实现盈亏 + 未平仓笔的 (当日期货价 − 开仓价) × 吨数 × 方向。
    与主表里「开平配对」总盈亏在区间末一致；不同于「仅在平仓日一次性画一跳」的旧画法。
    """
    q_each = float(lot_tons) * float(hedge_ratio)
    legs = []
    for _, r in df_editor.iterrows():
        db = _cell_date(r.get("购买日期"))
        ds = _cell_date(r.get("出售日期"))
        if db is None or ds is None:
            continue
        _, pf_b = lookup_spot_fut(sub, db)
        _, pf_s = lookup_spot_fut(sub, ds)
        if pf_b is None or pf_s is None:
            continue
        legs.append((db, ds, float(pf_b), float(pf_s)))

    out = []
    for _, row in sub.iterrows():
        d = pd.Timestamp(row["Date"]).date()
        fut_d = float(row["Futures"])
        total = 0.0
        for db, ds, pf_b, pf_s in legs:
            if d < db:
                continue
            if d >= ds:
                total += pnl_sign * (pf_s - pf_b) * q_each
            else:
                total += pnl_sign * (fut_d - pf_b) * q_each
        out.append(total / 10000.0)
    return out


def build_pairing_table(
    price_sub,
    df_editor,
    lot_tons,
    hedge_ratio,
    pnl_sign,
    buy_basis,
    buy_fut_mult,
    buy_fut_add,
):
    """每行购销：购入/售出结算价与利润；期货开平配对盈亏。"""
    rows = []
    t_spot = t_fut = 0.0
    for _, r in df_editor.iterrows():
        db = _cell_date(r.get("购买日期"))
        ds = _cell_date(r.get("出售日期"))
        n = len(rows) + 1
        ps_b = pf_b = ps_s = pf_s = None
        if db is not None:
            ps_b, pf_b = lookup_spot_fut(price_sub, db)
        if ds is not None:
            ps_s, pf_s = lookup_spot_fut(price_sub, ds)
        buy_cost_eff = None
        buy_note = ""
        if db is not None:
            if buy_basis == "futures" and pf_b is not None:
                buy_cost_eff = pf_b * buy_fut_mult + buy_fut_add
                buy_note = f"购:日期货×{buy_fut_mult:g}+{buy_fut_add:g}"
            elif buy_basis == "spot" and ps_b is not None:
                buy_cost_eff = ps_b
                buy_note = "购:CSV现货"
        m_sell = _row_float(r, "出售价期货倍数", _DEFAULT_SELL_FUT_MULT)
        a_sell = _row_float(r, "出售价加价(元/吨)", 0.0)
        ps_s_eff = None
        sell_src = ""
        if pf_s is not None:
            ps_s_eff = pf_s * m_sell + a_sell
            sell_src = f"售:日期货×{m_sell:g}+{a_sell:g}"
        spot_pnl = fut_pnl = None
        if buy_cost_eff is not None and ps_s_eff is not None:
            spot_pnl = (ps_s_eff - buy_cost_eff) * lot_tons
            t_spot += spot_pnl
        if pf_b is not None and pf_s is not None:
            fut_pnl = pnl_sign * (pf_s - pf_b) * lot_tons * hedge_ratio
            t_fut += fut_pnl
        tot = None
        if spot_pnl is not None and fut_pnl is not None:
            tot = spot_pnl + fut_pnl
        elif spot_pnl is not None:
            tot = spot_pnl
        elif fut_pnl is not None:
            tot = fut_pnl
        rows.append(
            {
                "轮次": n,
                "购入日": db.isoformat() if db else "",
                "购入价(实际)": buy_cost_eff,
                "购入说明": buy_note,
                "购买日期货(参考)": pf_b,
                "购买日现货(参考)": ps_b,
                "出售日": ds.isoformat() if ds else "",
                "出售日期货价": pf_s,
                "出售价期货倍数": m_sell,
                "出售价加价（元每吨）": a_sell,
                "出售价(实际)": ps_s_eff,
                "出售日现货(参考)": ps_s,
                "出售价说明": sell_src,
                "现货利润(万)": None if spot_pnl is None else round(spot_pnl / 10000, 4),
                "期货开空价": pf_b,
                "期货平仓价": pf_s,
                "期货盈亏(万)": None if fut_pnl is None else round(fut_pnl / 10000, 4),
                "合计利润(万)": None if tot is None else round(tot / 10000, 4),
            }
        )
    return pd.DataFrame(rows), t_spot, t_fut


sub, lo, hi = slice_price_for_events(price_df, events)
if sub.empty:
    st.error(f"购销事件对应日期区间 {lo} ~ {hi} 在 CSV 中无交易日数据。")
    st.stop()

by_d = build_by_d(events)

pair_df, total_spot_pair, total_fut_pair = build_pairing_table(
    sub,
    df_e,
    spot_tons,
    hedge_ratio,
    futures_pnl_sign,
    buy_basis,
    float(buy_fut_m),
    float(buy_fut_a),
)

res_spot, sum_spot, warn_spot = simulate_spot_only(sub, by_d, 0.0, pricing)
for w in warn_spot:
    st.warning(w)

st.markdown("---")
st.subheader("现货 / 期货 配对明细（主结果）")
st.caption(
    f"区间 **{lo} ~ {hi}**，共 **{len(sub)}** 个交易日；**{spot_tons:.0f} 吨** 现货（0 吨起、购买日一次买进，出售日一次卖清）。"
    "期货配对盈亏 = 方向系数 × (平仓期货价 − 开空价) × 仓位吨数 × 套保比例。"
)
st.dataframe(pair_df, hide_index=True, use_container_width=True)

m1, m2, m3 = st.columns(3)
with m1:
    st.metric("现货利润合计（配对）", f"{total_spot_pair / 10000:.2f} 万")
with m2:
    st.metric("期货盈亏合计（开平配对）", f"{total_fut_pair / 10000:.2f} 万")
with m3:
    st.metric("总利润（现货+期货配对）", f"{(total_spot_pair + total_fut_pair) / 10000:.2f} 万")

st.markdown("---")
st.subheader("逐日：盈亏曲线")
st.caption(
    "蓝线对**出售价相对当日期货价多出来的部分**（元/吨）× 吨数作图时摊销，例如期货 70000、倍数 1.1 即 **(77000−70000)×吨数**；"
    "从**卖出日**的日增量中扣除后，再按**购买日～出售日**之间的交易日均摊，曲线呈**逐步上移**而非最后一天突然抬升。"
    "其它盈亏（相对成本、现货盯市等）不变。**加价列**计入相对期货的差额。**明细表与 Excel 仍为仿真逐日原值**。"
)
cum_fut_wan = futures_mtm_cumulative_wan(sub, df_e, spot_tons, hedge_ratio, futures_pnl_sign)
_cum_fut_arr = np.asarray(cum_fut_wan, dtype=float)

_ensure_matplotlib_chinese_font()
_fp = _matplotlib_cjk_fontproperties()
V_spot = res_spot["Value_Change_Spot"].to_numpy(dtype=float)
_n_sp = len(V_spot)
if _n_sp == 0:
    spot_curve_wan = np.array([], dtype=float)
    _spot_lbl = "现货净资产变动（万元）"
else:
    d0 = np.diff(V_spot, prepend=0.0)
    spread_R = np.zeros(_n_sp, dtype=float)
    prem_on_sell = np.zeros(_n_sp, dtype=float)
    ts_norm = pd.to_datetime(res_spot["Date"]).dt.normalize()
    ts_np = ts_norm.to_numpy()
    for _, r in df_e.iterrows():
        db = _cell_date(r.get("购买日期"))
        ds = _cell_date(r.get("出售日期"))
        if db is None or ds is None or ds < db:
            continue
        _, fut_s = lookup_spot_fut(sub, ds)
        if fut_s is None:
            continue
        m_sell = _row_float(r, "出售价期货倍数", _DEFAULT_SELL_FUT_MULT)
        a_sell = _row_float(r, "出售价加价(元/吨)", 0.0)
        prem_pt = float(fut_s) * (float(m_sell) - 1.0) + float(a_sell)
        p_prem = prem_pt * float(spot_tons)
        if abs(p_prem) < 1e-9:
            continue
        t_sell = pd.Timestamp(ds).normalize().to_datetime64()
        m_sell_day = ts_np == t_sell
        if not m_sell_day.any():
            continue
        prem_on_sell[m_sell_day] += p_prem
        t_lo = pd.Timestamp(db).normalize().to_datetime64()
        m_win = (ts_np >= t_lo) & (ts_np <= t_sell)
        nn = int(m_win.sum())
        if nn <= 0:
            continue
        spread_R[m_win] += p_prem / nn
    d_adj = d0 - prem_on_sell + spread_R
    spot_curve_wan = np.cumsum(d_adj) / 10000.0
    _spot_lbl = "现货净资产变动（售价相对期货溢价按天摊销，万元）"

_m = min(len(spot_curve_wan), len(_cum_fut_arr))
if _m == 0:
    total_pnl_wan = np.array([], dtype=float)
    _date_total = res_spot["Date"].iloc[:0]
else:
    total_pnl_wan = spot_curve_wan[:_m] + _cum_fut_arr[:_m]
    _date_total = res_spot["Date"].iloc[:_m]

fig, ax = plt.subplots(figsize=(12, 5))
ax.plot(
    res_spot["Date"],
    spot_curve_wan,
    label=_spot_lbl,
    linewidth=2,
)
ax.plot(
    sub["Date"],
    _cum_fut_arr,
    label="期货盯市累计（相对各笔开仓价，万元）",
    linewidth=2,
    linestyle="--",
)
if len(total_pnl_wan) > 0:
    ax.plot(
        _date_total,
        total_pnl_wan,
        label="现货+期货合计（万元）",
        linewidth=2.2,
        color="tab:green",
    )
ax.axhline(0, color="black", linestyle=":", alpha=0.4)
if _fp:
    ax.set_ylabel("万元", fontproperties=_fp)
    ax.legend(loc="upper left", prop=_fp)
else:
    ax.set_ylabel("万元")
    ax.legend(loc="upper left")
plt.tight_layout()
st.pyplot(fig)
plt.close(fig)
st.caption(
    "**绿色**：蓝线现货 + **期货盯市累计** 的逐日合计（万元）。**橙色虚线**：期货盯市。"
    "蓝线作图时对 **(出售价−当日期货价)×吨** 做持仓期均摊，**期末与明细表「现货净资产变动」累计一致**；表格与 Excel 为仿真原值。"
)

st.markdown("---")
_price_title = f"{vn} — 期货与现货价格走势" if vn else "碳酸锂（或所上传品种）— 期货与现货价格走势"
st.subheader(_price_title)
st.caption("价格来自当前购销区间内的 CSV 列「现货价」「期货价」（元/吨）。")
_ensure_matplotlib_chinese_font()
_fp2 = _matplotlib_cjk_fontproperties()
fig_px, ax_px = plt.subplots(figsize=(12, 4.5))
ax_px.plot(sub["Date"], sub["Spot"], label="现货价格", color="tab:blue", linewidth=2)
ax_px.plot(
    sub["Date"],
    sub["Futures"],
    label="期货价格",
    color="tab:orange",
    linewidth=2,
    linestyle="--",
)
if _fp2:
    ax_px.set_ylabel("元/吨", fontproperties=_fp2)
    ax_px.legend(loc="best", prop=_fp2)
else:
    ax_px.set_ylabel("元/吨")
    ax_px.legend(loc="best")
ax_px.grid(True, alpha=0.3)
plt.tight_layout()
st.pyplot(fig_px)
plt.close(fig_px)

with st.expander("现货 — 逐日明细（中文列）"):
    st.caption(
        "**现货持仓浮动盈亏**（元）= 日末库存吨 ×（当日 CSV 现货价 − 加权平均成本）；无库存为 0；**负值**表示相对成本的浮亏。"
    )
    _spot_cn = _df_rename_cn(res_spot.copy(), CN_COL_现货逐日)
    _show_spot_cn = [
        "日期",
        "现货价",
        "期货价",
        "现货库存吨",
        "现货持仓浮动盈亏",
        "现货现金",
        "现货当日已实现盈亏",
        "现货净资产变动",
    ]
    st.dataframe(
        _spot_cn[[c for c in _show_spot_cn if c in _spot_cn.columns]],
        use_container_width=True,
        hide_index=True,
    )

res_margin = None
sum_margin = None
if show_margin_sim:
    res_margin, sum_margin, warn_m = simulate_hedged(sub, by_d, 0.0, pricing, margin_cfg)
    for w in warn_m:
        st.warning(w)
    st.markdown("---")
    st.subheader("保证金：补仓与出金信号（逐日仿真）")
    st.caption(
        "上图柱高 = 当日**补充保证金**或**提取出金**金额（万元），仅在触发补提金规则时出现；"
        "下图**风险度** = 期货账户权益 ÷ 占用保证金，低于侧栏「补金线倍数」时会补保证金，高于「提金线倍数」后可能出金。"
    )
    n_m = len(res_margin)
    idx_m = np.arange(n_m)
    inj_w = res_margin["Cash_Injection"].values / 10000.0
    out_w = res_margin["Cash_Withdrawal"].values / 10000.0
    _ensure_matplotlib_chinese_font()
    _fp = _matplotlib_cjk_fontproperties()
    fig_m, (ax_b, ax_r) = plt.subplots(
        2,
        1,
        figsize=(12, 7),
        sharex=True,
        gridspec_kw={"height_ratios": [2.2, 1]},
    )
    bw = 0.35
    ax_b.bar(idx_m - bw / 2, inj_w, bw, label="补充保证金（万元）", color="#c0392b", align="center")
    ax_b.bar(idx_m + bw / 2, out_w, bw, label="提取出金（万元）", color="#2980b9", align="center")
    if _fp:
        ax_b.set_ylabel("万元", fontproperties=_fp)
        ax_b.legend(loc="upper right", prop=_fp)
        ax_b.set_title("何时补保证金 / 何时出金（金额）", fontproperties=_fp)
        ax_r.set_ylabel("风险度\n（权益÷保证金）", fontproperties=_fp)
        ax_r.set_xlabel("日期", fontproperties=_fp)
    else:
        ax_b.set_ylabel("万元")
        ax_b.legend(loc="upper right")
        ax_b.set_title("何时补保证金 / 何时出金（金额）")
        ax_r.set_ylabel("风险度\n（权益÷保证金）")
        ax_r.set_xlabel("日期")
    ax_b.grid(True, axis="y", alpha=0.3)

    ax_r.plot(idx_m, res_margin["Risk_Degree"], color="#8e44ad", lw=1.2, marker="o", markersize=2)
    ax_r.grid(True, alpha=0.3)
    step_m = max(1, n_m // 14)
    ticks_m = idx_m[::step_m]
    ax_r.set_xticks(ticks_m)
    ax_r.set_xticklabels(
        [pd.Timestamp(res_margin["Date"].iloc[i]).strftime("%Y-%m-%d") for i in ticks_m],
        rotation=45,
        ha="right",
    )
    plt.tight_layout()
    st.pyplot(fig_m)
    plt.close(fig_m)

    st.subheader("逐日：所需占用保证金")
    st.caption(
        "按当日期货结算价、**现货库存×套保比例**、侧栏**保证金率**计算的基础占用（交易所规则简化模型）；纵轴为**万元**。"
    )
    _req_wan = res_margin["Margin_Required"].values / 10000.0
    _ensure_matplotlib_chinese_font()
    _fp_mr = _matplotlib_cjk_fontproperties()
    fig_mr, ax_mr = plt.subplots(figsize=(12, 4))
    ax_mr.fill_between(
        res_margin["Date"],
        _req_wan,
        alpha=0.25,
        color="#34495e",
    )
    ax_mr.plot(
        res_margin["Date"],
        _req_wan,
        color="#2c3e50",
        linewidth=2,
        label="占用保证金",
    )
    if _fp_mr:
        ax_mr.set_ylabel("万元", fontproperties=_fp_mr)
        ax_mr.legend(loc="best", prop=_fp_mr)
    else:
        ax_mr.set_ylabel("万元")
        ax_mr.legend(loc="best")
    ax_mr.grid(True, alpha=0.3)
    plt.tight_layout()
    st.pyplot(fig_mr)
    plt.close(fig_mr)

    mc1, mc2, mc3 = st.columns(3)
    with mc1:
        st.metric("补充保证金次数", int(sum_margin["inject_count"]))
    with mc2:
        st.metric("出金次数", int(sum_margin["withdraw_count"]))
    with mc3:
        st.metric(
            "期末期货权益（元）",
            f"{sum_margin['final_account_equity']:,.0f}",
        )

    with st.expander("保证金账户 — 逐日明细（中文列）"):
        _marg_cn = _df_rename_cn(res_margin.copy(), CN_COL_保证金逐日)
        _order_cn = [
            "日期",
            "现货价",
            "期货价",
            "现货库存吨",
            "期货账户权益",
            "占用保证金",
            "风险度",
            "当日补充保证金",
            "当日提取出金",
            "现货现金",
            "现货净资产",
            "含期货与资金流净资产变动",
            "基差",
            "现货当日已实现盈亏",
            "当日买入吨",
            "当日卖出吨",
        ]
        _cols_show = [c for c in _order_cn if c in _marg_cn.columns]
        st.dataframe(_marg_cn[_cols_show], use_container_width=True, hide_index=True)

buf = io.BytesIO()
with pd.ExcelWriter(buf, engine="openpyxl") as writer:
    pair_df.to_excel(writer, index=False, sheet_name="现货期货配对")
    summ = pd.DataFrame(
        [
            ["现货利润合计（万元）", total_spot_pair / 10000],
            ["期货盈亏合计（万元）", total_fut_pair / 10000],
            ["总利润（万元）", (total_spot_pair + total_fut_pair) / 10000],
        ],
        columns=["项目", "数值"],
    )
    summ.to_excel(writer, index=False, sheet_name="汇总")
    _df_rename_cn(res_spot.copy(), CN_COL_现货逐日).to_excel(writer, index=False, sheet_name="现货逐日")
    if res_margin is not None:
        _df_rename_cn(res_margin.copy(), CN_COL_保证金逐日).to_excel(
            writer, index=False, sheet_name="保证金逐日"
        )
buf.seek(0)
st.download_button(
    "下载 Excel",
    buf,
    file_name=f"现货期货_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)
