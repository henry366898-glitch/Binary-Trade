"""
Standalone MT5 connection check.

Reads credentials from .env via the project's settings module, then calls
MetaTrader5.initialize(). Prints account info on success, last_error on failure.
Run from the backend/ folder with the venv's python.
"""
import sys
from app.config import settings
import MetaTrader5 as mt5


def main() -> int:
    print(f"Connecting to MT5: login={settings.MT5_LOGIN}, server={settings.MT5_SERVER}")
    print(f"MT5 terminal must be running and logged in to the same account.")
    print()

    ok = mt5.initialize(
        login=settings.MT5_LOGIN,
        password=settings.MT5_PASSWORD,
        server=settings.MT5_SERVER,
    )
    if not ok:
        err = mt5.last_error()
        print(f"FAILED. mt5.last_error() = {err}")
        return 1

    acc = mt5.account_info()
    if acc is None:
        print("Initialized but account_info() returned None — terminal may not be logged in.")
        mt5.shutdown()
        return 1

    print("CONNECTED.")
    print(f"  Account login : {acc.login}")
    print(f"  Server        : {acc.server}")
    print(f"  Name          : {acc.name}")
    print(f"  Balance       : {acc.balance} {acc.currency}")
    print(f"  Leverage      : 1:{acc.leverage}")
    print(f"  Trade allowed : {acc.trade_allowed}")

    print()
    print("Sample tick fetch (first 3 configured symbols):")
    for sym in settings.SYMBOLS[:3]:
        if not mt5.symbol_select(sym, True):
            print(f"  {sym:8s}  could not select symbol")
            continue
        t = mt5.symbol_info_tick(sym)
        if t:
            print(f"  {sym:8s}  bid={t.bid}  ask={t.ask}")
        else:
            print(f"  {sym:8s}  no tick yet (symbol may not be active on this server)")

    mt5.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
