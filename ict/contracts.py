"""Contract specs used for costs and sizing: tick size (price units) and tick value (USD).

Standard CME Group specifications for the full-size contracts (micro bitcoin /
ether for crypto). Verify against CME before trading real money.
"""
from __future__ import annotations

TICK = {
    # Equity indices
    "NQ": (0.25, 5.0), "ES": (0.25, 12.5), "YM": (1.0, 5.0), "RTY": (0.10, 5.0), "NKD": (5.0, 25.0),
    # Metals
    "GC": (0.10, 10.0), "SI": (0.005, 25.0), "HG": (0.0005, 12.5), "PL": (0.10, 5.0),
    # Energy
    "CL": (0.01, 10.0), "NG": (0.001, 10.0), "HO": (0.0001, 4.2), "RB": (0.0001, 4.2),
    # Currencies
    "6E": (0.00005, 6.25), "6B": (0.0001, 6.25), "6J": (0.0000005, 6.25), "6A": (0.00005, 5.0),
    "6C": (0.00005, 5.0), "6S": (0.00005, 6.25), "6N": (0.00005, 5.0), "6M": (0.00001, 5.0),
    # Rates
    "ZB": (1 / 32, 31.25), "UB": (1 / 32, 31.25), "ZN": (1 / 64, 15.625), "TN": (1 / 64, 15.625),
    "ZF": (1 / 128, 7.8125), "ZT": (1 / 256, 7.8125),
    # Agriculture (grain prices in cents)
    "ZC": (0.25, 12.5), "ZS": (0.25, 12.5), "ZW": (0.25, 12.5), "ZL": (0.01, 6.0), "ZM": (0.10, 10.0),
    "HE": (0.025, 10.0), "LE": (0.025, 10.0),
    # Crypto (micro contracts)
    "MBT": (5.0, 0.50), "MET": (0.50, 0.05),
}


def cost_in_r(sym: str, risk_pts: float, commission_usd: float = 4.5, slippage_ticks: float = 1.0) -> float:
    """Round-trip cost of one contract as a fraction of the trade's risk (1R)."""
    size, value = TICK[sym]
    risk_usd = risk_pts / size * value
    return (commission_usd + slippage_ticks * value) / risk_usd if risk_usd > 0 else float("nan")
