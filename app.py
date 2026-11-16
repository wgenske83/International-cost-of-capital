"""International Cost of Capital | Kellogg International Finance."""
import io
import re
from datetime import datetime, timezone

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title='International Cost of Capital', page_icon='🌐', layout='wide')
BETA_URL = 'https://pages.stern.nyu.edu/~adamodar/pc/datasets/betas.xls'
SPREAD_URL = 'https://pages.stern.nyu.edu/adamodar/New_Home_Page/datafile/ratings.html'
OECD_URL = 'https://www.oecd.org/en/publications/corporate-tax-statistics-2024_9c27d6e8-en/full-report/statutory-corporate-income-tax-rates_440f9286.html'
BONDS_URL = 'https://tradingeconomics.com/bonds'
# 2026 OECD figures transcribed from the supplied lecture, p.11; NOT a live OECD fetch.
TAX_FALLBACK = {'United States':25.5,'Canada':26.0,'Colombia':35.0,'United Kingdom':25.0,'Germany':30.1,'France':36.1,'Japan':29.7,'Australia':30.0,'India':25.2,'Brazil':34.0,'Mexico':30.0,'Poland':19.0,'China':25.0,'Switzerland':19.5,'Ireland':12.5,'Italy':27.8,'Spain':25.0,'Netherlands':25.8,'Sweden':20.6,'Norway':22.0,'Denmark':22.0,'Finland':20.0,'South Korea':27.5,'Portugal':29.5,'Chile':27.0,'South Africa':27.0,'Singapore':17.0,'New Zealand':28.0,'Austria':23.0,'Belgium':25.0,'Greece':22.0,'Hungary':9.0,'Turkey':25.0,'Thailand':20.0,'Indonesia':22.0}
ALIASES = {'US':'United States','USA':'United States','United States':'United States','UK':'United Kingdom','Britain':'United Kingdom','South Korea':'South Korea','Korea':'South Korea','Türkiye':'Turkey','Czech Republic':'Czechia','Russian Federation':'Russia'}
HEADERS = {'User-Agent':'Mozilla/5.0 (compatible; educational-research/1.0)'}

def fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=22)
    r.raise_for_status()
    return r

def pct(x):
    if pd.isna(x): return None
    m = re.search(r'-?\d+(?:\.\d+)?',str(x).replace(',',''))
    return float(m.group()) if m else None

def norm(s):
    s = re.sub(r'\s+',' ',str(s)).strip()
    return ALIASES.get(s,s)

@st.cache_data(ttl=86400,show_spinner=False)
def get_betas():
    raw=fetch(BETA_URL).content
    sheets=pd.read_excel(io.BytesIO(raw),sheet_name=None,header=None,engine='xlrd')
    for sheet in sheets.values():
        for i in range(min(20,len(sheet))):
            labels=[str(x).lower().strip() for x in sheet.iloc[i].tolist()]
            industry=next((j for j,v in enumerate(labels) if v in ('industry name','industry')),None)
            beta=next((j for j,v in enumerate(labels) if 'unlevered beta' in v and 'cash' not in v),None)
            if industry is not None and beta is not None:
                rows=sheet.iloc[i+1:,[industry,beta]].copy()
                rows.columns=['Industry','Unlevered beta']
                rows['Unlevered beta']=pd.to_numeric(rows['Unlevered beta'],errors='coerce')
                rows=rows.dropna(subset=['Unlevered beta'])
                rows['Industry']=rows['Industry'].astype(str).str.strip()
                rows=rows[~rows['Industry'].str.lower().isin(['total market','nan','total'])]
                if len(rows)>10:return rows.drop_duplicates('Industry').sort_values('Industry').reset_index(drop=True)
    raise ValueError('Could not identify the unlevered-beta column in the Damodaran workbook.')

@st.cache_data(ttl=86400,show_spinner=False)
def get_spread():
    tables=pd.read_html(io.StringIO(fetch(SPREAD_URL).text))
    for t in tables:
        for _,row in t.iterrows():
            cells=[str(v) for v in row.tolist()]
            if any(re.search(r'Baa2\s*/\s*BBB\b',v,re.I) for v in cells):
                vals=[pct(v) for v in cells]
                # The table typically has rating, interest coverage, default spread; spread is last numeric column.
                candidates=[v for v in vals[1:] if v is not None]
                if candidates:
                    spread=candidates[-1]
                    if 0<spread<20:return spread
    raise ValueError('Could not locate Baa2/BBB spread; enter a manual override.')

@st.cache_data(ttl=3600,show_spinner=False)
def get_yields():
    tables=pd.read_html(io.StringIO(fetch(BONDS_URL).text))
    result={}
    for table in tables:
        for _,row in table.iterrows():
            cells=[str(v).strip() for v in row.tolist()]
            if not cells:continue
            label=cells[0]
            # Trading Economics bond rows normally begin with e.g. 'United States 10Y'.
            match=re.search(r'(.+?)\s+(?:10Y|10-Year|10 Year)\b',label,re.I)
            if match:
                country=norm(match.group(1).strip())
            elif label in TAX_FALLBACK or label in ('Colombia','Brazil','United States'):
                # The /bonds overview table lists benchmark 10Y yields by country.
                country=norm(label)
            else:
                continue
            # Yield is first numeric field following the country label.
            for v in cells[1:]:
                y=pct(v)
                if y is not None and -5<y<100:
                    result[country]=y
                    break
    if 'United States' not in result:
        raise ValueError('Trading Economics bond table was not available in a recognizable format.')
    return result

@st.cache_data(ttl=86400,show_spinner=False)
def get_oecd():
    # OECD publication table layouts can change. Accept only clearly labeled statutory combined rates.
    tables=pd.read_html(io.StringIO(fetch(OECD_URL).text))
    out={}
    for t in tables:
        cols=[str(c).lower() for c in t.columns]
        name_col=next((i for i,c in enumerate(cols) if 'country' in c or 'jurisdiction' in c),None)
        rate_col=next((i for i,c in enumerate(cols) if ('combined' in c or 'statutory' in c) and ('rate' in c or 'cit' in c)),None)
        if name_col is None or rate_col is None:continue
        for _,row in t.iterrows():
            name=norm(row.iloc[name_col]); rate=pct(row.iloc[rate_col])
            if name and rate is not None and 0<=rate<=60:out[name]=rate
    if len(out)<8:raise ValueError('OECD page did not expose a machine-readable combined statutory-rate table.')
    return out

def calculate(beta_u,tax,erp,debt,rf_us,rf_foreign,spread_us,spread_foreign=None):
    """All rates are decimal fractions; matches Rebelo slides 574, 577, 582–585."""
    if not 0<=debt<1:raise ValueError('Debt share must be below 100%.')
    factor=(1+rf_foreign)/(1+rf_us)
    beta_e=beta_u*(1+(1-tax)*debt/(1-debt))
    ke_us=rf_us+beta_e*erp
    kd_us=rf_us+spread_us
    wacc_us=(1-debt)*ke_us+debt*kd_us*(1-tax)
    ke_f=(1+ke_us)*factor-1
    sf=spread_us*factor if spread_foreign is None else spread_foreign
    kd_f=rf_foreign+sf
    wacc_f=(1-debt)*ke_f+debt*kd_f*(1-tax)
    return {'Levered beta':beta_e,'USD cost of equity':ke_us,'USD pretax cost of debt':kd_us,'USD after-tax debt cost':kd_us*(1-tax),'USD WACC':wacc_us,'Foreign cost of equity':ke_f,'Foreign pretax cost of debt':kd_f,'Foreign after-tax debt cost':kd_f*(1-tax),'Foreign WACC':wacc_f,'Foreign borrowing spread':sf,'Currency factor':factor}

st.title('🌐 International Cost of Capital')
st.caption('USD vs. foreign-currency financing • Sergio Rebelo international valuation methodology')
with st.sidebar:
    st.header('Project assumptions')
    if st.button('🔄 Refresh source data',use_container_width=True):
        get_betas.clear();get_spread.clear();get_yields.clear();get_oecd.clear();st.rerun()

sources={};errors={}
for key,fn in [('Industry betas',get_betas),('USD BBB spread',get_spread),('Government yields',get_yields),('OECD taxes',get_oecd)]:
    try:sources[key]=fn()
    except Exception as exc:errors[key]=str(exc)

betas=sources.get('Industry betas',pd.DataFrame(columns=['Industry','Unlevered beta']))
yields=sources.get('Government yields',{})
taxes=sources.get('OECD taxes',TAX_FALLBACK)
with st.sidebar:
    industries=sorted(set(betas['Industry'].tolist()+['Software (System & Application)']))
    default_industry='Software (System & Application)'
    industry=st.selectbox('Industry',industries,index=industries.index(default_industry))
    countries=sorted(set(yields)|set(taxes)|{'United States','Colombia'})
    country=st.selectbox('Target country',countries,index=countries.index('United States'))
    erp=st.number_input('Equity risk premium (%)',0.0,40.0,6.5,0.1)/100
    debt=st.slider('Target debt financing (%)',0,99,30)/100
    tax_choice=st.radio('Corporate tax rate applied to BOTH currencies',['U.S. tax rate','Target-country tax rate'],horizontal=False)
    st.subheader('Manual data overrides')
    st.caption('Switch on to replace a downloaded value. Blank source values require an override.')
    def override(label,auto,default,min_value=0.,max_value=100.):
        enabled=st.toggle('Override '+label,value=auto is None,key='toggle_'+label)
        if enabled:
            val=st.number_input(label,min_value=min_value,max_value=max_value,value=float(auto if auto is not None else default),step=0.1,key='num_'+label)
            return val,'Manual override'
        return auto,'Automatic'
    match=betas[betas['Industry']==industry]
    beta_auto=float(match.iloc[0]['Unlevered beta']) if len(match) else None
    beta,bsrc=override('Unlevered beta',beta_auto,1.0,0,10)
    tax_country='United States' if tax_choice=='U.S. tax rate' else country
    tax,tsrc=override('Corporate tax rate (%)',taxes.get(tax_country),25.5)
    spread,ssrc=override('USD BBB spread (percentage points)',sources.get('USD BBB spread'),1.5)
    rf_us,usrc=override('U.S. 10Y yield (%)',yields.get('United States'),4.0,-5,100)
    rf_f,fsrc=override(f'{country} 10Y yield (%)',yields.get(country),4.0,-5,100)
    f_override=st.toggle('Override foreign-currency BBB spread',value=False)
    f_spread=st.number_input('Foreign spread (percentage points)',min_value=0.0,max_value=100.0,value=1.5,step=0.1) if f_override else None

missing=[name for name,val in [('Unlevered beta',beta),('Tax rate',tax),('USD spread',spread),('U.S. yield',rf_us),('Foreign yield',rf_f)] if val is None]
if missing:
    st.error('Missing data: '+', '.join(missing)+'. Enable the corresponding manual overrides to calculate.')
    st.stop()
res=calculate(beta,tax/100,erp,debt,rf_us/100,rf_f/100,spread/100,None if f_spread is None else f_spread/100)
fmt=lambda x:f'{x:.4%}'
left,right=st.columns(2)
with left:
    st.subheader('🇺🇸 U.S. dollars (USD)')
    st.metric('WACC',fmt(res['USD WACC']))
    st.metric('Cost of equity',fmt(res['USD cost of equity']))
    st.metric('Pretax cost of debt',fmt(res['USD pretax cost of debt']))
    st.caption('After-tax cost of debt: '+fmt(res['USD after-tax debt cost']))
with right:
    st.subheader(f'🌍 {country} currency')
    st.metric('WACC',fmt(res['Foreign WACC']),delta=f"{(res['Foreign WACC']-res['USD WACC'])*100:+.2f} pp",delta_color='off')
    st.metric('Cost of equity',fmt(res['Foreign cost of equity']))
    st.metric('Pretax cost of debt',fmt(res['Foreign pretax cost of debt']))
    st.caption('After-tax cost of debt: '+fmt(res['Foreign after-tax debt cost']))
st.info(f"Levered beta: **{res['Levered beta']:.4f}** · Tax rate: **{tax:.2f}%** ({tax_country}) · Debt: **{debt:.0%}** · ERP: **{erp:.2%}** · Foreign BBB spread: **{res['Foreign borrowing spread']:.4%}** ({'manual' if f_override else 'auto-converted'})")

with st.expander('📐 Formulas and assumptions',expanded=False):
    st.latex(r'D/E=d/(1-d),\qquad \beta_E=\beta_U[1+(1-\tau)D/E]')
    st.latex(r'R_e=R_f+\beta_E ERP,\qquad R_d=R_f+s')
    st.latex(r'WACC=(1-d)R_e+dR_d(1-\tau)')
    st.latex(r'F=\frac{1+R_f^*}{1+R_f},\quad R_e^*=(1+R_e)F-1,\quad s^*=sF')
    st.latex(r'R_d^*=R_f^*+s^*,\qquad WACC^*=(1-d)R_e^*+dR_d^*(1-\tau)')
    st.write('Government bond yields are risk-free proxies, not guaranteed default-free rates. The model uses U.S. industry beta, one ERP, one tax rate and one debt share in both currencies. Foreign spread override changes only the foreign borrowing cost. No separate country equity risk premium is included. Currency conversion relies on the interest-rate/relative-PPP approximation.')

st.subheader('All-industry comparison')
if len(betas):
    rows=[]
    for _,r in betas.iterrows():
        z=calculate(float(r['Unlevered beta']),tax/100,erp,debt,rf_us/100,rf_f/100,spread/100,None if f_spread is None else f_spread/100)
        rows.append({'Industry':r['Industry'],'Unlevered beta':float(r['Unlevered beta']),'Levered beta':z['Levered beta'],'USD cost of equity (%)':100*z['USD cost of equity'],'USD WACC (%)':100*z['USD WACC'],f'{country} cost of equity (%)':100*z['Foreign cost of equity'],f'{country} WACC (%)':100*z['Foreign WACC']})
    comparison=pd.DataFrame(rows)
    st.dataframe(comparison,hide_index=True,use_container_width=True)
    st.download_button('⬇️ Download all-industry comparison (CSV)',comparison.to_csv(index=False).encode(),'all_industries_wacc.csv','text/csv')
else:st.warning('Industry comparison requires a successful Damodaran beta download.')

st.subheader('Source status and dates')
now=datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
st.caption('Session checked: '+now+'. This is a retrieval time, NOT the underlying publication/market observation date. Confirm source observation dates on the linked pages.')
for name,url in [('Industry betas',BETA_URL),('USD BBB spread',SPREAD_URL),('Government yields',BONDS_URL),('OECD taxes',OECD_URL)]:
    status='Retrieved (cached up to 24h)' if name in sources else 'Unavailable: '+errors.get(name,'unknown')
    if name=='Government yields' and name in sources:status='Retrieved (cached up to 1h)'
    if name=='OECD taxes' and name not in sources:status+='; using explicitly labeled 2026 lecture fallback where available'
    st.write(f'**{name}:** [{url}]({url}) — {status}')
st.caption('OECD fallback rates are transcribed from the supplied 2026 lecture slide, not a live OECD observation. The requested 2024 OECD URL may not expose an extractable 2026 table. No fabricated live market data is substituted when a yield or beta fetch fails.')
inputs={'industry':industry,'country':country,'beta_unlevered':beta,'tax_percent':tax,'tax_jurisdiction':tax_country,'erp_percent':erp*100,'debt_percent':debt*100,'us_10y_percent':rf_us,'foreign_10y_percent':rf_f,'us_bbb_spread_percent':spread,'foreign_spread_override_percent':f_spread,'source_check_utc':now,'beta_source':bsrc,'tax_source':tsrc,'spread_source':ssrc,'us_yield_source':usrc,'foreign_yield_source':fsrc}
output=pd.DataFrame([dict(inputs,**res)])
st.download_button('⬇️ Download current scenario (CSV)',output.to_csv(index=False).encode(),'cost_of_capital_scenario.csv','text/csv')

with st.expander('✅ Built-in verification tests'):
    example=calculate(.8,.35,.065,.3,.04,.12,.015)
    checks={'Colombia USD WACC ≈ 8.5265%':abs(example['USD WACC']-.085265)<.000001,'Colombia COP WACC ≈ 16.0670%':abs(example['Foreign WACC']-.16067)<.000001,'Equal yields → equal currency results':abs(calculate(.8,.35,.065,.3,.04,.04,.015)['USD WACC']-calculate(.8,.35,.065,.3,.04,.04,.015)['Foreign WACC'])<1e-12,'Zero debt → WACC equals equity cost':abs(calculate(.8,.35,.065,0,.04,.12,.015)['USD WACC']-calculate(.8,.35,.065,0,.04,.12,.015)['USD cost of equity'])<1e-12,'Foreign spread override leaves USD unchanged':abs(example['USD WACC']-calculate(.8,.35,.065,.3,.04,.12,.015,.05)['USD WACC'])<1e-12}
    for label,passed in checks.items():st.write(('✅' if passed else '❌')+' '+label)
