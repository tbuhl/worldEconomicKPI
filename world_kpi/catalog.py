from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Indicator:
    key: str
    name: str
    category: str
    series_id: str
    unit: str
    frequency: str
    transform: str = "level"
    periods_per_year: int = 12
    risk_direction: str = "high"
    weight: float = 1.0
    why: str = ""
    watch: str = ""
    source_name: str = "FRED"

    @property
    def source_url(self) -> str:
        return f"https://fred.stlouisfed.org/series/{self.series_id}"


# The catalogue intentionally mixes fast stress signals with slower vulnerability measures.
# Composite scores are calculated inside each pillar first, so a category with many series does
# not dominate simply because it has more rows.
FRED_INDICATORS: tuple[Indicator, ...] = (
    # Growth and labour
    Indicator("sahm", "Sahm recession rule", "Growth & labour", "SAHMREALTIME", "pp", "Monthly", risk_direction="high", weight=1.4, why="A broad labour-market recession trigger, not a forecast.", watch="0.50 pp has historically marked recession onset."),
    Indicator("unemployment", "Unemployment rate", "Growth & labour", "UNRATE", "%", "Monthly", risk_direction="high", weight=1.2, why="Rising unemployment can turn a slowdown into a negative income-demand loop.", watch="Watch the rate of change, not just the level."),
    Indicator("claims", "Initial jobless claims · YoY", "Growth & labour", "ICSA", "%", "Weekly", "yoy_pct", 52, "high", 1.0, "Claims usually turn before payrolls.", "A persistent rise matters more than one noisy week."),
    Indicator("payrolls", "Nonfarm payrolls · YoY", "Growth & labour", "PAYEMS", "%", "Monthly", "yoy_pct", 12, "low", 1.1, "Employment growth supports income and debt service.", "Near-zero or negative growth is a strong warning."),
    Indicator("job_openings", "Job openings · YoY", "Growth & labour", "JTSJOL", "%", "Monthly", "yoy_pct", 12, "low", 0.7, "Labour demand often cools before layoffs accelerate.", "Fast declines can precede weaker hiring."),
    Indicator("real_gdp", "Real GDP growth", "Growth & labour", "A191RL1Q225SBEA", "% ann.", "Quarterly", risk_direction="low", weight=1.1, why="The broadest measure of current real activity.", watch="Two negative quarters are useful context, not the official recession definition."),
    Indicator("industrial", "Industrial production · YoY", "Growth & labour", "INDPRO", "%", "Monthly", "yoy_pct", 12, "low", 0.9, "Captures the cyclical goods-producing economy.", "Sustained contraction has accompanied past downturns."),
    Indicator("retail", "Retail sales · YoY", "Growth & labour", "RSAFS", "%", "Monthly", "yoy_pct", 12, "low", 0.7, "A timely nominal spending pulse.", "Interpret beside inflation: nominal growth can overstate real demand."),
    Indicator("sentiment", "Consumer sentiment", "Growth & labour", "UMCSENT", "index", "Monthly", risk_direction="low", weight=0.6, why="Household confidence influences discretionary demand.", watch="Useful as confirmation; it can stay depressed without recession."),
    Indicator("permits", "Building permits · YoY", "Growth & labour", "PERMIT", "%", "Monthly", "yoy_pct", 12, "low", 0.8, "Housing is highly rate-sensitive and often leads the cycle.", "Deep, persistent contraction is more informative than one month."),
    Indicator("recession_prob", "Smoothed recession probability", "Growth & labour", "RECPROUSM156N", "%", "Monthly", risk_direction="high", weight=0.7, why="A model-based coincident cross-check.", watch="Model output is revised and is not a certainty."),

    # Inflation and policy
    Indicator("cpi", "Headline CPI · YoY", "Inflation & policy", "CPIAUCSL", "%", "Monthly", "yoy_pct", 12, "high", 1.0, "Inflation constrains central-bank support during stress.", "Persistent inflation matters more than a one-month shock."),
    Indicator("core_cpi", "Core CPI · YoY", "Inflation & policy", "CPILFESL", "%", "Monthly", "yoy_pct", 12, "high", 1.1, "A slower-moving measure of underlying price pressure.", "Sticky services inflation can keep real rates restrictive."),
    Indicator("core_pce", "Core PCE · YoY", "Inflation & policy", "PCEPILFE", "%", "Monthly", "yoy_pct", 12, "high", 1.2, "The Federal Reserve's preferred underlying inflation gauge.", "Compare with the 2% longer-run inflation objective."),
    Indicator("fed_funds", "Effective federal funds rate", "Inflation & policy", "DFF", "%", "Daily", risk_direction="high", weight=0.8, why="The front line of U.S. monetary restraint.", watch="The impact arrives with long and variable lags."),
    Indicator("real_10y", "10-year real Treasury yield", "Inflation & policy", "DFII10", "%", "Daily", risk_direction="high", weight=1.0, why="A high real discount rate pressures long-duration assets and borrowers.", watch="Rapid changes can matter as much as the absolute level."),
    Indicator("breakeven_5y5y", "5y5y inflation expectation", "Inflation & policy", "T5YIFR", "%", "Daily", risk_direction="high", weight=0.7, why="Market pricing of longer-run inflation expectations.", watch="A sharp rise limits easing; a collapse can signal demand stress."),
    Indicator("mortgage", "30-year mortgage rate", "Inflation & policy", "MORTGAGE30US", "%", "Weekly", risk_direction="high", weight=0.8, why="Transmits policy into housing affordability and refinancing.", watch="Compare with household income growth and housing turnover."),

    # Sovereign and rates
    Indicator("ust_3m", "3-month Treasury yield", "Sovereign & rates", "DGS3MO", "%", "Daily", risk_direction="high", weight=0.5, why="The cash hurdle rate and near-term policy expectation.", watch="A high short rate can expose weak funding models."),
    Indicator("ust_2y", "2-year Treasury yield", "Sovereign & rates", "DGS2", "%", "Daily", risk_direction="high", weight=0.6, why="Sensitive to the expected policy path.", watch="Fast repricing can tighten financial conditions abruptly."),
    Indicator("ust_10y", "10-year Treasury yield", "Sovereign & rates", "DGS10", "%", "Daily", risk_direction="high", weight=0.9, why="The global benchmark discount rate.", watch="A disorderly rise is more dangerous than a growth-led gradual rise."),
    Indicator("ust_30y", "30-year Treasury yield", "Sovereign & rates", "DGS30", "%", "Daily", risk_direction="high", weight=0.8, why="Reflects long-run inflation, term premium and fiscal supply concerns.", watch="Watch alongside auctions, term premium and the dollar."),
    Indicator("curve_2s10s", "10y minus 2y curve", "Sovereign & rates", "T10Y2Y", "pp", "Daily", risk_direction="low", weight=1.0, why="Inversion has often preceded U.S. recessions.", watch="Risk often materializes after the curve re-steepens."),
    Indicator("curve_3m10y", "10y minus 3m curve", "Sovereign & rates", "T10Y3M", "pp", "Daily", risk_direction="low", weight=1.1, why="A widely studied recession signal.", watch="It is a horizon signal, not a countdown clock."),
    Indicator("term_premium", "10-year term premium", "Sovereign & rates", "THREEFFTP10", "%", "Daily", risk_direction="high", weight=0.9, why="Compensation for duration risk; can rise with supply and uncertainty.", watch="A jump tightens conditions even without a policy hike."),
    Indicator("debt_gdp", "Federal debt held by public / GDP", "Sovereign & rates", "GFDEGDQ188S", "% GDP", "Quarterly", risk_direction="high", weight=1.2, why="Captures the public debt burden relative to the tax base.", watch="Debt level alone does not time a crisis; interest cost and currency regime matter."),
    Indicator("interest_growth", "Federal interest payments · YoY", "Sovereign & rates", "A091RC1Q027SBEA", "%", "Quarterly", "yoy_pct", 4, "high", 1.0, "Fast interest-cost growth reduces fiscal room.", "Nominal growth can be large even when debt service remains manageable."),
    Indicator("japan_10y", "Japan long-term government yield", "Sovereign & rates", "IRLTLT01JPM156N", "%", "Monthly", risk_direction="high", weight=0.8, why="Higher JGB yields can encourage Japanese capital to return home.", watch="Track with USD/JPY and actual TIC holdings rather than assuming sales."),
    Indicator("usdjpy", "JPY per USD · YoY", "Sovereign & rates", "DEXJPUS", "%", "Daily", "yoy_pct", 252, "two_sided", 0.6, "Large FX moves can change hedged Treasury economics for Japanese investors.", "Direction and hedging costs matter; extremes in either direction can destabilize."),

    # Credit and financial plumbing
    Indicator("hy_oas", "U.S. high-yield spread", "Credit & plumbing", "BAMLH0A0HYM2", "pp", "Daily", risk_direction="high", weight=1.4, why="A direct market price of lower-quality corporate credit risk.", watch="Rapid widening is a stronger stress signal than a high but stable level."),
    Indicator("ig_oas", "U.S. investment-grade spread", "Credit & plumbing", "BAMLC0A0CM", "pp", "Daily", risk_direction="high", weight=1.0, why="Shows whether stress is spreading to stronger borrowers.", watch="Low spreads can mean resilience—or underpriced risk."),
    Indicator("nfci", "Chicago Fed financial conditions", "Credit & plumbing", "NFCI", "z-score", "Weekly", risk_direction="high", weight=1.2, why="Combines money, debt, equity and banking conditions.", watch="Positive values are tighter than average."),
    Indicator("stlfsi", "St. Louis Fed financial stress", "Credit & plumbing", "STLFSI4", "z-score", "Weekly", risk_direction="high", weight=1.2, why="A broad, high-frequency market stress composite.", watch="Spikes usually show stress already underway."),
    Indicator("sloos", "Banks tightening C&I standards", "Credit & plumbing", "DRTSCILM", "% net", "Quarterly", risk_direction="high", weight=1.1, why="Bank willingness to lend transmits financial stress into the real economy.", watch="Positive values mean more banks are tightening."),
    Indicator("card_delinquency", "Credit-card delinquency rate", "Credit & plumbing", "DRCCLACBS", "%", "Quarterly", risk_direction="high", weight=0.8, why="A window into pressure on revolving-credit borrowers.", watch="Composition and post-pandemic normalization complicate comparisons."),
    Indicator("mortgage_delinquency", "Mortgage delinquency rate", "Credit & plumbing", "DRSFRMACBS", "%", "Quarterly", risk_direction="high", weight=0.8, why="Housing-credit deterioration amplified the 2008 crisis.", watch="Underwriting and fixed-rate mortgage structure differ materially from 2008."),
    Indicator("bank_loans", "Commercial bank loans · YoY", "Credit & plumbing", "TOTLL", "%", "Weekly", "yoy_pct", 52, "low", 0.7, "Weak credit creation can reinforce a slowdown.", "Demand and supply both affect this series."),

    # Markets and global transmission
    Indicator("vix", "Equity volatility · VIX", "Markets & global", "VIXCLS", "index", "Daily", risk_direction="high", weight=1.1, why="Options-implied near-term equity volatility.", watch="A low VIX is not safety; it can coexist with high vulnerability."),
    Indicator("dollar", "Trade-weighted U.S. dollar · YoY", "Markets & global", "DTWEXBGS", "%", "Daily", "yoy_pct", 252, "two_sided", 0.9, "A surging dollar tightens global dollar funding and pressures foreign borrowers.", "Fast appreciation is usually the more damaging tail."),
    Indicator("oil", "WTI crude oil · YoY", "Markets & global", "DCOILWTICO", "%", "Daily", "yoy_pct", 252, "two_sided", 0.7, "Oil spikes squeeze consumers; collapses can reveal demand stress.", "Interpret the direction and cause, not just the percentile."),
    Indicator("copper", "Copper price · YoY", "Markets & global", "PCOPPUSDM", "%", "Monthly", "yoy_pct", 12, "low", 0.6, "A rough global industrial-demand barometer.", "Supply disruptions can overwhelm the demand signal."),
    Indicator("policy_uncertainty", "U.S. policy uncertainty", "Markets & global", "USEPUINDXD", "index", "Daily", risk_direction="high", weight=0.6, why="Policy uncertainty can delay investment and raise risk premia.", watch="Event spikes are common; persistence is more consequential."),
    Indicator("ecb_rate", "ECB deposit facility rate", "Markets & global", "ECBDFR", "%", "Daily", risk_direction="high", weight=0.5, why="A key global funding and demand setting outside the U.S.", watch="Read alongside growth and bank funding conditions."),
)


FRED_BY_KEY = {indicator.key: indicator for indicator in FRED_INDICATORS}
CATEGORIES = tuple(dict.fromkeys(indicator.category for indicator in FRED_INDICATORS))


MARKET_METRIC_META: dict[str, dict[str, str | float]] = {
    "spy_drawdown": {"name": "S&P 500 drawdown", "category": "Markets & global", "unit": "%", "direction": "low", "weight": 1.0, "why": "Measures loss from the prior all-time high."},
    "spy_volatility": {"name": "S&P 500 realized volatility", "category": "Markets & global", "unit": "% ann.", "direction": "high", "weight": 0.8, "why": "Shows stress already appearing in daily prices."},
    "qqq_spy": {"name": "Nasdaq 100 / S&P 500 relative trend", "category": "AI capital cycle", "unit": "% YoY", "direction": "high", "weight": 0.8, "why": "A proxy for technology leadership and crowding."},
    "breadth": {"name": "Equal-weight / S&P 500 breadth", "category": "AI capital cycle", "unit": "% YoY", "direction": "low", "weight": 1.0, "why": "Weak breadth means fewer large firms carry the index."},
    "semis_return": {"name": "Semiconductors 12-month return", "category": "AI capital cycle", "unit": "%", "direction": "high", "weight": 0.7, "why": "Tracks exuberance in the main AI picks-and-shovels trade."},
    "semis_drawdown": {"name": "Semiconductor drawdown", "category": "AI capital cycle", "unit": "%", "direction": "low", "weight": 0.9, "why": "A fast break in semiconductors can expose crowded positioning."},
    "ai_basket_return": {"name": "AI equity basket 12-month return", "category": "AI capital cycle", "unit": "%", "direction": "high", "weight": 0.9, "why": "A transparent price-based froth proxy, not a valuation model."},
    "ai_basket_vol": {"name": "AI equity basket volatility", "category": "AI capital cycle", "unit": "% ann.", "direction": "high", "weight": 0.8, "why": "Crowded narratives often become fragile as volatility rises."},
}
