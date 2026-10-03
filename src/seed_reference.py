import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()
engine = create_engine(os.environ["DATABASE_URL"])


def isin_is_valid(isin: str) -> bool:
    if len(isin) != 12 or not isin.isalnum():
        return False
    digits = "".join(str(int(ch, 36)) for ch in isin.upper())
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


INSTRUMENTS = [
    ("HSBA", "HSBC Holdings", "GB0005405286"),
    ("AZN", "AstraZeneca", "GB0009895292"),
    ("SHEL", "Shell", "GB00BP6MXD84"),
    ("BP.", "BP", "GB0007980591"),
    ("BARC", "Barclays", "GB0031348658"),
    ("LLOY", "Lloyds Banking Group", "GB0008706128"),
    ("DGE", "Diageo", "GB0002374006"),
    ("GSK", "GSK", "GB00BN7SWP63"),
    ("RIO", "Rio Tinto", "GB0007188757"),
    ("VOD", "Vodafone Group", "GB00BH4HKS39"),
    ("NG.", "National Grid", "GB00BDR05C01"),
    ("TSCO", "Tesco", "GB0008847096"),
    ("BA.", "BAE Systems", "GB0002634946"),
    ("GLEN", "Glencore", "JE00B4T3BW64"),
    ("RKT", "Reckitt Benckiser", "GB00B24CGK77"),
    ("RR.", "Rolls-Royce Holdings", "GB00B63H8491"),
    ("STAN", "Standard Chartered", "GB0004082847"),
    ("LGEN", "Legal & General", "GB0005603997"),
    ("CPG", "Compass Group", "GB00BD6K4575"),
]

COUNTERPARTIES = [
    ("Northbridge Capital", "GB", "ASSET_MANAGER"),
    ("Thames Pension Trust", "GB", "PENSION_FUND"),
    ("Albion Securities", "GB", "BROKER_DEALER"),
    ("Caledonia Fund Partners", "GB", "HEDGE_FUND"),
    ("Mersey Investment Bank", "GB", "BANK"),
    ("Lakeland Asset Management", "GB", "ASSET_MANAGER"),
    ("Hudson Crest Trading", "US", "BROKER_DEALER"),
    ("Redwood Global Advisors", "US", "ASSET_MANAGER"),
    ("Liffey Capital Markets", "IE", "BROKER_DEALER"),
    ("Rhine Valley Bank", "DE", "BANK"),
    ("Seine Gestion", "FR", "ASSET_MANAGER"),
    ("Alpine Wealth Partners", "CH", "HEDGE_FUND"),
    ("Orion Retirement Fund", "NL", "PENSION_FUND"),
    ("Harbourline Securities", "GB", "BROKER_DEALER"),
    ("Granite Peak Investments", "US", "HEDGE_FUND"),
]

for ticker, name, isin in INSTRUMENTS:
    if not isin_is_valid(isin):
        raise ValueError(f"Invalid ISIN check digit for {ticker}: {isin}")

with engine.begin() as conn:
    for ticker, name, isin in INSTRUMENTS:
        conn.execute(
            text(
                "INSERT INTO instruments (instrument_id, isin, ticker, instrument_name, asset_type, currency) "
                "VALUES (:id, :isin, :ticker, :name, 'EQUITY', 'GBP') "
                "ON CONFLICT (instrument_id) DO NOTHING"
            ),
            {"id": f"INS_{ticker.strip('.')}", "isin": isin, "ticker": ticker, "name": name},
        )
    for i, (name, country, ctype) in enumerate(COUNTERPARTIES, start=1):
        conn.execute(
            text(
                "INSERT INTO counterparties (counterparty_id, counterparty_name, country, counterparty_type) "
                "VALUES (:id, :name, :country, :ctype) "
                "ON CONFLICT (counterparty_id) DO NOTHING"
            ),
            {"id": f"CP{i:03d}", "name": name, "country": country, "ctype": ctype},
        )

with engine.connect() as conn:
    n_i = conn.execute(text("SELECT COUNT(*) FROM instruments")).scalar()
    n_c = conn.execute(text("SELECT COUNT(*) FROM counterparties")).scalar()
print(f"instruments: {n_i}, counterparties: {n_c}")