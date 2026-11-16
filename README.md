# International Cost of Capital

A Streamlit app for comparing project financing costs in USD and another country's currency, following Sergio Rebelo's 2026 International Valuation slides (especially slides 574, 577–585).

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy

1. Create a public GitHub repository and upload `app.py`, `requirements.txt`, and `README.md`.
2. Sign in to [Streamlit Community Cloud](https://share.streamlit.io/), choose **Create app**, select your repository, branch `main`, and entry point `app.py`.
3. Deploy and copy the live URL into your submission.

## Defaults

Industry: Software (System & Application); country: United States; tax jurisdiction: United States; ERP: 6.5%; debt share: 30%.

## Data and limitations

- [Damodaran U.S. industry unlevered betas](https://pages.stern.nyu.edu/~adamodar/pc/datasets/betas.xls): downloads an Excel file and locates the unlevered-beta column.
- [Damodaran Baa2/BBB spread](https://pages.stern.nyu.edu/adamodar/New_Home_Page/datafile/ratings.html): parses the ratings table.
- [Trading Economics 10-year yields](https://tradingeconomics.com/bonds): scrapes the public bond table; table format/anti-bot restrictions may change. Manual yield overrides are provided.
- [OECD corporate tax rates](https://www.oecd.org/en/publications/corporate-tax-statistics-2024_9c27d6e8-en/full-report/statutory-corporate-income-tax-rates_440f9286.html): attempts to parse combined statutory tax-rate tables. If unavailable, the app uses explicitly labeled 2026 lecture-slide fallback values, not live OECD data.

**Important:** The source-check timestamp is not the data observation date. Confirm the publication/market observation date at the source. Tax fallback coverage is limited. Some non-OECD countries may require manual entry. A displayed 10-year sovereign yield is a risk-free *proxy*, not necessarily free of credit risk. No separate country equity risk premium is modeled. The app does not infer the currency ticker for every country.

## Model

Let `d` = target debt share, `tau` = chosen tax rate, `ERP` = equity risk premium, `s` = USD BBB spread, `Rf` = USD government yield and `Rf*` = foreign yield.

- `D/E = d/(1-d)`
- `betaE = betaU * (1+(1-tau)*D/E)`
- `Re = Rf + betaE*ERP`
- `Rd = Rf + s`
- `WACC = (1-d)*Re + d*Rd*(1-tau)`
- `F = (1+Rf*)/(1+Rf)`
- `Re* = (1+Re)*F-1`
- `foreign_spread = USD_spread * F` (unless overridden)
- `Rd* = Rf* + foreign_spread`
- `WACC* = (1-d)*Re* + d*Rd_foreign*(1-tau)`

## Verification

Use the **Built-in verification tests** section, and the companion `verification.xlsx` spreadsheet. Professor's Colombia example: betaU 0.8, debt 30%, tax 35%, ERP 6.5%, U.S. yield 4%, Colombia yield 12%, USD spread 1.5%; USD WACC 8.5265%, COP WACC 16.0670%. Other tests: equal yields, zero debt, foreign spread override isolation.

## Caveats

Live scrapers are brittle and can fail due to changed source layouts or blocked requests. A failed live source is flagged; the user can override missing values. Never describe a manual input or lecture fallback as live. The app is educational and does not supply investment advice.
