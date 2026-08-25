import numpy as np
import pandas as pd
import yfinance as yf
import requests
from io import StringIO


def get_sp500():

    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Referer": "https://www.google.com/",
    "Upgrade-Insecure-Requests": "1",
}
    # Define headers to mimic a web browser
    # session = requests.Session()
    # session.headers.update({
    #     'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
    # })

    # Fetch the content of the URL with headers
    response = requests.get(url, headers=headers)

    # Use pandas to read HTML directly from the response text
    tables = pd.read_html(StringIO(response.text))
    sp500_df = tables[0]

    sp500_symbols = sp500_df["Symbol"].tolist()

    return sp500_symbols

def historical_erp(start="1990-01-01", end=None, market_ticker="^GSPC", rf_ticker="^TNX"):
    market = yf.download(market_ticker, start=start, end=end, progress=False, auto_adjust=True)["Close"]
    market = market.squeeze()  # ensures plain Series, not 1-col DataFrame

    years = (market.index[-1] - market.index[0]).days / 365.25
    market_cagr = float((market.iloc[-1] / market.iloc[0]) ** (1 / years) - 1)

    rf_series = yf.Ticker(rf_ticker).history(period="5d")["Close"].squeeze()
    rf = float(rf_series.iloc[-1] / 100)

    erp = market_cagr - rf
    return market_cagr, rf, erp



def cost_of_debt_and_data(stock):

    
    
    """
    Returns:
        tuple: (metrics_dict, income_statement_df, balance_sheet_df)
    """
    # 1. Fetch stock using the modern Ticker object
    ticker = stock
    
    # 2. Extract standard financial DataFrames directly
    income_stmt = ticker.income_stmt
    balance_sh = ticker.balance_sheet
    
    # 3. Dynamic row targeting for Interest Expense
    interest_expense = 0
    possible_interest_rows = [
        "Interest Expense Non Operating", 
        "Interest Expense", 
        "Net Non Operating Interest Income Expense"
    ]
    
    found_row = "None"
    for row_name in possible_interest_rows:
        if row_name in income_stmt.index:
            interest_expense = abs(income_stmt.loc[row_name].iloc[0])
            found_row = row_name
            break
            
    # 4. Target Debt and Tax metrics safely
    st_debt = balance_sh.loc["Current Debt"].iloc[0] if "Current Debt" in balance_sh.index else 0
    lt_debt = balance_sh.loc["Long Term Debt"].iloc[0] if "Long Term Debt" in balance_sh.index else 0
    total_debt = st_debt + lt_debt

    ebt = income_stmt.loc["Pretax Income"].iloc[0] if "Pretax Income" in income_stmt.index else 0
    tax_provision = income_stmt.loc["Tax Provision"].iloc[0] if "Tax Provision" in income_stmt.index else 0
    
    effective_tax_rate = tax_provision / ebt if ebt > 0 else 0.21

    # 5. Cost of Debt Calculations
    pre_tax_cost = interest_expense / total_debt if total_debt > 0 else 0
    after_tax_cost = pre_tax_cost * (1 - effective_tax_rate)

    # 6. Package calculations into a clean dictionary
    metrics = {
        "statement_date": income_stmt.columns[0].strftime('%Y-%m-%d'),
        "interest_expense_row_used": found_row,
        "interest_expense": interest_expense,
        "total_debt": total_debt,
        "effective_tax_rate": effective_tax_rate,
        "pre_tax_cost_of_debt": pre_tax_cost,
        "after_tax_cost_of_debt": after_tax_cost
    }

    return metrics, income_stmt, balance_sh


def get_exact_dcf_fcf_margin(stock,income_stmt, cashflow):
    # 1. Initialize the Ticker object
    cash_flow = cashflow
    ticker_symbol = stock
    
    try:
        # 3. Extract exact rows needed for the formula
        revenue = income_stmt.loc['Total Revenue']
        ebit = income_stmt.loc['EBIT']
        tax_provision = income_stmt.loc['Tax Provision']
        pretax_income = income_stmt.loc['Pretax Income']
        
        # Cash Flow items (yfinance stores Capex as negative or positive depending on version; we ensure correct signs)
        da = cash_flow.loc['Depreciation And Amortization']
        capex = cash_flow.loc['Capital Expenditure'].abs()  # Treat Capex as a positive outflow value for subtraction
        nwc_change = cash_flow.loc['Change In Working Capital']
        
    except KeyError as e:
        return f"Error: Required financial row {e} not found for {ticker_symbol}."
    
    # 4. Calculate the Effective Tax Rate safely (Tax Provision / Pretax Income)
    # Fill 0 if pretax income is negative or zero to avoid division errors
    effective_tax_rate = (tax_provision / pretax_income).apply(lambda x: max(0, x) if x > 0 else 0)
    
    # 5. Apply the exact DCF Unlevered FCF formula
    nopat = ebit * (1 - effective_tax_rate)
    unlevered_fcf = nopat + da - capex - nwc_change
    
    # 6. Calculate the FCF Margin for DCF
    fcf_margin = (unlevered_fcf / revenue) * 100
    
    # 7. Structure the final DataFrame
    df_result = pd.DataFrame({
        'Total Revenue': revenue,
        'EBIT': ebit,
        'Effective Tax Rate (%)': effective_tax_rate * 100,
        'D&A': da,
        'CapEx': capex,
        'NWC Change': nwc_change,
        'Unlevered FCF': unlevered_fcf,
        'DCF FCF Margin (%)': fcf_margin
    })
    
    # Sort chronologically (oldest year to newest year)
    df_result = df_result.sort_index(ascending=True)
    
    return df_result.round(2)



def get_unsplitted_value(ticker_symbol: str):
    """
    Calculates the unadjusted value of an original share before splits.
    
    """
    try:
        # Enforce string type and convert to uppercase
        symbol_str = str(ticker_symbol).upper()
        
        # Initialize the yfinance Ticker object using the clean string
        ticker_obj = yf.Ticker(symbol_str)
        
        # Fetch current price safely
        hist = ticker_obj.history(period="1d")
        if hist.empty:
            print(f"Error: No data found for ticker '{symbol_str}'")
            return None
        current_price = float(hist['Close'].iloc[-1])
        
        # Calculate split multiplier
        splits = ticker_obj.splits
        cumulative_factor = 1.0
        if not splits.empty:
            for split_ratio in splits:
                cumulative_factor *= float(split_ratio)
                
        # Reverse the split math
        unadjusted_price = current_price * cumulative_factor
        
        # Print results safely using the symbol_str variable
        print(f"=== {symbol_str} ===")
        print(f"Current Market Price:  ${current_price:.2f}")
        print(f"Total Split Multiplier: {cumulative_factor:.2f}x")
        print(f"Unadjusted Share Value: ${unadjusted_price:.2f}\n")
        
        return unadjusted_price

    except Exception as e:
        print(f"An error occurred: {str(e)}")
        return None






#placeholder 

# def get_tax_rate(stock,income_statement):
    
    
#     # 3. Target the most recent year's column (the first column)
#     latest_year = income_statement.columns[0]
    
#     try:
#         # Yahoo Finance standardizes these exact string indexes
#         tax_provision = income_statement.loc['Tax Provision', latest_year]
#         pretax_income = income_statement.loc['Pretax Income', latest_year]
        
#         # 4. Handle edge case: Pre-tax loss (negative EBT)
#         if pretax_income <= 0:
#             print(f"⚠️ Warning: {stock} had negative pretax income. Falling back to default statutory rate.")
#             return 0.2100
            
#         # 5. Calculate and round to 4 decimal places
#         tax_rate = round(tax_provision / pretax_income, 4)
#         return tax_rate
        
#     except KeyError as e:
#         print(f"❌ Error: Could not find required row {e} in the financial data.")
#         return None
