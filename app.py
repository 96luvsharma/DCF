import streamlit as st

dcf = st.Page("dcf.py", title="DCF Calculation")
my_page2 = st.Page("page1.py", title="Portfolio Optimization")
pg = st.navigation([dcf, my_page2])

st.set_page_config(page_title="My Finance Projects")

pg.run()
