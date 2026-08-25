import numpy as np
import pandas as pd
import yfinance as yf
import matplotlib.pyplot as plt
import requests
from io import StringIO
import streamlit as st
import dcf_functions as xr


st.set_page_config(layout="wide")

if "show_settings" not in st.session_state:
    st.session_state.show_settings = False

# Settings toggle button
if st.button("Settings", icon=":material/settings:"):
    st.session_state.show_settings = not st.session_state.show_settings

# Conditional display of settings panel
if st.session_state.show_settings:
    with st.expander("App Settings", expanded=True):
        theme = st.selectbox("Theme", ["Light", "Dark"])
        refresh_rate = st.slider("Refresh Rate (s)", 1, 60, 5)
        debug_mode = st.checkbox("Debug Mode")
        
        if st.button("Save Settings"):
            st.success("Settings saved!")
            st.session_state.show_settings = False

@st.cache_data
def getsp500():
    sp500 = xr.get_sp500()
    return sp500

sp500 = getsp500()

TICKER = st.selectbox("Choose a Stock Symbol", sp500, index=None,
    placeholder="Select a stock symbol.")

if 'clicked' not in st.session_state:
    st.session_state.clicked = False

def click_button():
    st.session_state.clicked = True

st.button('Get Info', on_click=click_button)

if st.session_state.clicked:

    if TICKER == None:
        st.write("Waiting for selection...")
    else:
        # @st.cache_data
        # def getinfo(TICKER):
        stock = yf.Ticker(TICKER)
        info = stock.info
        financials = stock.financials
        cashflow = stock.cashflow
        # return stock, info, financials, cashflow

        # stock, info, financials, cashflow = getinfo(TICKER)
        # TaxRate = st.slider("Tax Rate",min_value=0, max_value=100)

        company_name = info.get("longName", TICKER)
        current_price = info.get("currentPrice") or info.get("regularMarketPrice")
        shares_outstanding = info.get("sharesOutstanding")
        beta = info.get("beta")
        market_cap = info.get("marketCap", 0)
        total_debt = info.get("totalDebt", 0)
        total_cash = info.get("totalCash", 0)


        Company_Data = {
            "Company": [company_name], "Current Price": [f"${current_price:,.2f}"],
            "Shares Outstanding": [f"${shares_outstanding:,.2f}"], "Beta": [f"{beta*100:.2f}"],
            "Market Cap": [f"${market_cap:,.2f}"], "Total Debt": [f"${total_debt:,.2f}"],
            "Total Cash": [f"${total_cash:,.2f}"]
        }


        st.table(Company_Data, border="horizontal")

        market_return, risk_free_rate, erp = xr.historical_erp()

        col1, col2 = st.columns(2)

        with col1:
            hist = {"Market CAGR": [market_return], "Risk Free Rate": [risk_free_rate],
                    "Historical ERP": [erp]
                }
            st.table(hist)

        with col2:
            stock_metrics, raw_income_stmt, raw_balance_sheet = xr.cost_of_debt_and_data(stock)
            metrics_df = pd.DataFrame.from_dict(stock_metrics, orient="index", columns=["Value"])
            df_metrics = metrics_df.reset_index().rename(columns={"index": "Metric"})
            display_names = {
                "statement_date": "📅 Statement Date",
                "interest_expense_row_used": "🔎 Row Matched",
                "interest_expense": "💵 Annual Interest",
                "total_debt": "💳 Total Outstanding Debt",
                "effective_tax_rate": "🏛️ Effective Tax Rate",
                "pre_tax_cost_of_debt": "📈 Pre-Tax Cost of Debt",
                "after_tax_cost_of_debt": "📉 After-Tax Cost of Debt (WACC Input)"
            }
            df_metrics["Metric"] = df_metrics["Metric"].map(display_names)

            # 3. Apply custom string formatting to the "Value" column
            def format_rows(row):
                metric = row["Metric"]
                val = row["Value"]
                
                # Format currencies
                if "Annual Interest" in metric or "Total Outstanding Debt" in metric:
                    return f"${val:,.2f}"
                # Format percentages
                elif "Rate" in metric or "Cost of Debt" in metric:
                    return f"{val * 100:.2f}%"
                # Leave dates and text descriptions as strings
                return str(val)

            df_metrics["Value"] = df_metrics.apply(format_rows, axis=1)

            st.dataframe(df_metrics)

        Years = 5
        Long_term_growth = 0.04
        Equity_risk_premium = erp
        Risk_free_rate = risk_free_rate
        Cost_of_debt = round(stock_metrics["after_tax_cost_of_debt"], 4)
        Tax_rate = metrics_df["Value"].iloc[4]

        # Historical Growth
        revenues_hist = financials.loc["Total Revenue"].sort_index()
        current_revenue = float(revenues_hist.iloc[-1])
        hist_growth = float(revenues_hist.iloc[-1] / revenues_hist.iloc[-2] - 1) if len(revenues_hist) >= 2 else 0.05
        hist_growth = float(np.clip(hist_growth, -0.05, 0.35))   # sanity clamp

        revenue_growth_rates = list(np.linspace(hist_growth, Long_term_growth, Years))

        #FCF
        op_cf = cashflow.loc["Operating Cash Flow"].iloc[0]
        capex = cashflow.loc["Capital Expenditure"].iloc[0]
        fcf = xr.get_exact_dcf_fcf_margin(stock,raw_income_stmt, cashflow)

        st.dataframe(fcf)

        net_debt = float(total_debt - total_cash)

        # --- WACC ---
        cost_of_equity = Risk_free_rate + beta * erp
        total_capital = market_cap + total_debt
        equity_weight = market_cap / total_capital if total_capital else 1.0
        debt_weight = total_debt / total_capital if total_capital else 0.0
        wacc = (equity_weight * cost_of_equity) + ((debt_weight * Cost_of_debt) * (1 - Tax_rate))
        wacc = float(np.clip(wacc, 0.05, 0.20))

        terminal_growth_rate = 0.025
        assert wacc > terminal_growth_rate, "WACC must be greater than terminal growth rate."

        fcf_margin = fcf["DCF FCF Margin (%)"].iloc[1]

        table_f = {"Starting Revenue Growth ": f"{hist_growth:.2%}",
                   "Long Term Growth": f"{Long_term_growth:.2%}",
                   "FCF Margin": f"{fcf_margin:.2f}%",
                   "WACC (CAPM Estimate)": f"{wacc:.2%}",
                   "Net Debt": f"{net_debt:,.0f}"}
        col_3, col_4 = st.columns(2)
        with col_3:
            st.table(table_f)


        revenues, fcfs = [], []
        revenue = current_revenue
        for growth in revenue_growth_rates:
            revenue = revenue * (1 + growth)
            fcf = revenue * fcf_margin
            revenues.append(revenue)
            fcfs.append(fcf)

        projection_df = pd.DataFrame({
            "Year": [f"Year {i+1}" for i in range(Years)],
            "Growth Rate": revenue_growth_rates,
            "Projected Revenue": revenues,
            "Projected FCF": fcfs,
        })
        
        discount_factors = [1 / (1 + wacc) ** (i + 1) for i in range(Years)]
        pv_fcfs = [fcf * df for fcf, df in zip(fcfs, discount_factors)]

        projection_df["Discount Factor"] = discount_factors
        projection_df["PV of FCF"] = pv_fcfs

        with col_4:
            st.dataframe(projection_df, hide_index= True)    

        price_adjusted_for_splits = current_price
        final_fcf = fcfs[-1]
        terminal_value = (final_fcf * (1 + terminal_growth_rate)) / (wacc - terminal_growth_rate)
        pv_terminal_value = terminal_value / (1 + wacc) ** Years

        sum_pv_fcf = sum(pv_fcfs)
        enterprise_value = sum_pv_fcf + pv_terminal_value
        equity_value = enterprise_value - net_debt
        fair_value_per_share = equity_value / shares_outstanding
        upside = (fair_value_per_share / price_adjusted_for_splits) - 1
        verdict = "UNDERVALUED" if upside > 0 else "OVERVALUED"     

        final_outcome = {"Company": f"{company_name}", "Current_Price": f"${current_price:,.2f}",
                 "Fair Value per Share": f"${fair_value_per_share:,.2f}",
                 "Implied Upside/Downside": f"{upside * 100:.2f}% ({verdict})"}

        st.table(final_outcome)

        if verdict == "UNDERVALUED":
            st.title(f"{company_name} is :blue[{verdict}] :heavy_check_mark:")
        elif verdict == "OVERVALUED":
            st.title(f"{company_name} is :blue[{verdict}] :x:")

        def calculate_fair_value(wacc_input, tgr_input):
            revenue = current_revenue
            fcfs_local = []
            for growth in revenue_growth_rates:
                revenue = revenue * (1 + growth)
                fcfs_local.append(revenue * fcf_margin)

            pv_fcfs_local = [
                fcf / (1 + wacc_input) ** (i + 1) for i, fcf in enumerate(fcfs_local)
            ]

            tv = (fcfs_local[-1] * (1 + tgr_input)) / (wacc_input - tgr_input)
            pv_tv = tv / (1 + wacc_input) ** len(revenue_growth_rates)

            ev = sum(pv_fcfs_local) + pv_tv
            eq = ev - net_debt
            return eq / shares_outstanding

        wacc_range = np.round(np.arange(wacc - 0.02, wacc + 0.025, 0.01), 4)
        tgr_range = np.round(np.arange(terminal_growth_rate - 0.01, terminal_growth_rate + 0.0125, 0.005), 4)

        sensitivity = pd.DataFrame(index=wacc_range, columns=tgr_range, dtype=float)

        for w in wacc_range:
            for g in tgr_range:
                if w <= g:
                    sensitivity.loc[w, g] = np.nan   # invalid combination, formula breaks
                else:
                    sensitivity.loc[w, g] = calculate_fair_value(w, g)

        sensitivity.index = [f"{w:.1%}" for w in sensitivity.index]
        sensitivity.columns = [f"{g:.1%}" for g in sensitivity.columns]
        sensitivity.index.name = "WACC"
        sensitivity.columns.name = "Terminal Growth"

        fig, ax = plt.subplots(figsize=(9, 6))
        data = sensitivity.values.astype(float)
        im = ax.imshow(data, cmap="RdYlGn", aspect="auto")

        ax.set_xticks(range(len(sensitivity.columns)))
        ax.set_xticklabels(sensitivity.columns)
        ax.set_yticks(range(len(sensitivity.index)))
        ax.set_yticklabels(sensitivity.index)
        ax.set_xlabel("Terminal Growth Rate")
        ax.set_ylabel("WACC")
        ax.set_title(f"{company_name} — DCF Sensitivity\nFair Value per Share ($)")

        for i in range(data.shape[0]):
            for j in range(data.shape[1]):
                val = data[i, j]
                if not np.isnan(val):
                    ax.text(j, i, f"{val:,.2f}", ha="center", va="center", fontsize=8)

        fig.colorbar(im, ax=ax, label="Fair Value / Share ($)")
        plt.tight_layout()
        st.pyplot(fig)

        st.session_state.clicked = False

            
