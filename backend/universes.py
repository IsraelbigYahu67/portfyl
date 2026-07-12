"""Screener universes: static constituent lists for the preset indices.

Static on purpose — the screener is an idea-discovery tool, not an index
tracker, so a list that trails index rebalances by a few months is fine and
costs no network call, no API key, and no scraping fragility. Symbols use
Yahoo Finance spelling (class shares dashed: BRK-B, BF-B). A delisted or
renamed ticker degrades gracefully: its row errors and is dropped from
results by the screener.

Lists as of late 2025. To refresh, replace a list wholesale (order doesn't
matter; duplicates are tolerated — the screener dedupes).
"""

# S&P 500 constituents (~500 names).
SP500 = [
    # Information Technology
    "AAPL", "MSFT", "NVDA", "AVGO", "ORCL", "CRM", "ADBE", "AMD", "ACN", "CSCO",
    "INTU", "IBM", "NOW", "QCOM", "TXN", "AMAT", "PANW", "PLTR", "MU", "ANET",
    "LRCX", "KLAC", "SNPS", "CDNS", "APH", "MSI", "ADI", "CRWD", "FTNT", "NXPI",
    "MCHP", "TEL", "ROP", "IT", "DELL", "HPQ", "HPE", "GLW", "WDC", "STX",
    "NTAP", "ZBRA", "KEYS", "TDY", "TYL", "PTC", "CDW", "EPAM", "JBL", "TRMB",
    "VRSN", "AKAM", "FFIV", "GEN", "SWKS", "ON", "MPWR", "TER", "FSLR", "ENPH",
    "WDAY", "DDOG", "APP", "GDDY", "CTSH", "FICO", "ADSK", "INTC", "SMCI",
    # Communication Services
    "GOOGL", "GOOG", "META", "NFLX", "TMUS", "DIS", "CMCSA", "T", "VZ", "CHTR",
    "EA", "TTWO", "WBD", "OMC", "IPG", "LYV", "MTCH", "FOXA", "FOX", "NWSA",
    "NWS", "TKO",
    # Consumer Discretionary
    "AMZN", "TSLA", "HD", "MCD", "BKNG", "NKE", "LOW", "TJX", "SBUX", "ORLY",
    "MAR", "CMG", "AZO", "ROST", "HLT", "DHI", "LEN", "GM", "F", "YUM",
    "RCL", "CCL", "NCLH", "EBAY", "DRI", "LULU", "ULTA", "EXPE", "ABNB", "GRMN",
    "APTV", "TSCO", "PHM", "NVR", "BBY", "KMX", "POOL", "LVS", "WYNN", "MGM",
    "CZR", "DPZ", "WSM", "DASH", "TPR", "RL", "HAS", "MHK", "LKQ", "GPC",
    # Consumer Staples
    "PG", "COST", "WMT", "KO", "PEP", "PM", "MO", "MDLZ", "CL", "KMB",
    "GIS", "KHC", "HSY", "STZ", "SYY", "KDP", "KR", "TGT", "DG", "DLTR",
    "ADM", "CHD", "MKC", "CLX", "EL", "COTY", "CAG", "CPB", "HRL", "SJM",
    "TSN", "LW", "BG", "TAP", "KVUE",
    # Energy
    "XOM", "CVX", "COP", "EOG", "SLB", "PSX", "MPC", "VLO", "OXY", "WMB",
    "KMI", "OKE", "HAL", "BKR", "DVN", "FANG", "CTRA", "EQT", "TRGP", "APA",
    "EXE", "TPL",
    # Financials
    "BRK-B", "JPM", "V", "MA", "BAC", "WFC", "GS", "MS", "SPGI", "AXP",
    "BLK", "C", "SCHW", "PGR", "CB", "MMC", "ICE", "FI", "KKR", "APO",
    "BX", "COF", "PYPL", "AON", "MET", "AIG", "TRV", "ALL", "PRU", "AFL",
    "BK", "STT", "TFC", "USB", "PNC", "MTB", "FITB", "HBAN", "RF", "CFG",
    "KEY", "NTRS", "AMP", "RJF", "TROW", "BEN", "IVZ", "CINF", "L", "GL",
    "HIG", "WRB", "ACGL", "EG", "FDS", "MCO", "MSCI", "NDAQ", "CME", "CBOE",
    "COIN", "SYF", "PFG", "BRO", "AJG", "AIZ", "GPN", "FIS", "JKHY", "CPAY",
    "ERIE",
    # Health Care
    "LLY", "UNH", "JNJ", "ABBV", "MRK", "TMO", "ABT", "DHR", "PFE", "AMGN",
    "ISRG", "SYK", "BSX", "VRTX", "GILD", "REGN", "MDT", "BMY", "CI", "ELV",
    "CVS", "ZTS", "BDX", "HCA", "MCK", "CAH", "COR", "GEHC", "IDXX", "IQV",
    "A", "RMD", "EW", "DXCM", "BIIB", "MRNA", "ILMN", "WAT", "MTD", "STE",
    "ZBH", "BAX", "HOLX", "LH", "DGX", "PODD", "ALGN", "TECH", "CRL", "HSIC",
    "VTRS", "SOLV", "MOH", "CNC", "UHS", "DVA", "INCY", "WST", "BIO",
    # Industrials
    "GE", "CAT", "RTX", "UNP", "HON", "ETN", "BA", "DE", "LMT", "UPS",
    "PH", "ADP", "TT", "ITW", "GD", "NOC", "MMM", "CSX", "EMR", "FDX",
    "NSC", "WM", "CARR", "PCAR", "JCI", "URI", "GWW", "CMI", "PWR", "LHX",
    "AME", "OTIS", "IR", "ROK", "FAST", "VRSK", "EFX", "CTAS", "ODFL", "RSG",
    "DAL", "UAL", "LUV", "AAL", "ALK", "EXPD", "CHRW", "JBHT", "DOV", "XYL",
    "HUBB", "WAB", "TDG", "HWM", "AXON", "LDOS", "TXT", "HII", "SNA", "PNR",
    "ALLE", "MAS", "BLDR", "IEX", "NDSN", "SWK", "ROL", "PAYX", "PAYC", "BR",
    "VLTO", "GEV", "UBER", "J", "FTV", "AOS",
    # Materials
    "LIN", "SHW", "APD", "ECL", "FCX", "NEM", "CTVA", "DOW", "DD", "PPG",
    "NUE", "VMC", "MLM", "IP", "PKG", "SW", "BALL", "AVY", "CF", "MOS",
    "LYB", "ALB", "IFF", "EMN", "STLD", "AMCR",
    # Real Estate
    "PLD", "AMT", "EQIX", "WELL", "SPG", "PSA", "O", "DLR", "CCI", "EXR",
    "AVB", "VICI", "IRM", "CBRE", "VTR", "EQR", "SBAC", "WY", "INVH", "ESS",
    "MAA", "ARE", "KIM", "DOC", "UDR", "CPT", "HST", "REG", "BXP", "FRT",
    "CSGP",
    # Utilities
    "NEE", "SO", "DUK", "CEG", "SRE", "AEP", "D", "PCG", "EXC", "XEL",
    "ED", "PEG", "WEC", "AWK", "DTE", "ES", "ETR", "FE", "AEE", "CMS",
    "CNP", "ATO", "NI", "LNT", "EVRG", "PPL", "NRG", "VST", "AES", "PNW",
]

# NASDAQ-100 constituents (~100 names).
NASDAQ100 = [
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "GOOG", "AVGO", "TSLA", "NFLX",
    "COST", "ASML", "AMD", "PEP", "LIN", "CSCO", "TMUS", "INTU", "QCOM", "TXN",
    "AMGN", "ISRG", "HON", "BKNG", "AMAT", "ADBE", "PANW", "GILD", "ADI", "VRTX",
    "SBUX", "MU", "INTC", "LRCX", "KLAC", "MELI", "CTAS", "PDD", "REGN", "SNPS",
    "CDNS", "MDLZ", "MAR", "CSX", "ORLY", "CRWD", "ABNB", "FTNT", "NXPI", "ADSK",
    "ROP", "PCAR", "MNST", "WDAY", "CPRT", "PAYX", "ROST", "KDP", "ODFL", "FAST",
    "AEP", "CHTR", "EA", "GEHC", "VRSK", "EXC", "CTSH", "XEL", "KHC", "CCEP",
    "IDXX", "TTWO", "DXCM", "ZS", "AZN", "FANG", "BKR", "ON", "CSGP", "DDOG",
    "TEAM", "MRVL", "BIIB", "WBD", "GFS", "CDW", "DASH", "TTD", "ARM", "APP",
    "LULU", "PLTR", "AXON", "MSTR",
]

# S&P 500 Dividend Aristocrats: 25+ consecutive years of dividend growth (~65 names).
DIVIDEND_ARISTOCRATS = [
    "MMM", "AOS", "ABT", "ABBV", "AFL", "APD", "ALB", "AMCR", "ADP", "BDX",
    "BF-B", "BRO", "CAH", "CAT", "CB", "CHD", "CHRW", "CINF", "CTAS", "CLX",
    "KO", "CL", "CVX", "DOV", "ECL", "EMR", "ERIE", "ESS", "EXPD", "XOM",
    "FDS", "FAST", "FRT", "BEN", "GD", "GPC", "HRL", "ITW", "JNJ", "KMB",
    "LOW", "MKC", "MCD", "MDT", "NEE", "NDSN", "NUE", "PNR", "PEP", "PG",
    "O", "PPG", "ROP", "SPGI", "SHW", "SJM", "SWK", "SYY", "TGT", "TROW",
    "LIN", "WMT", "WST", "GWW",
]

# Tech mega-caps: intentionally small — it doubles as the screener's fallback
# universe, so keep it cheap to scan.
TECH_LARGE = [
    "AAPL", "MSFT", "NVDA", "AVGO", "ORCL", "CRM", "AMD", "ADBE", "CSCO", "ACN",
]
