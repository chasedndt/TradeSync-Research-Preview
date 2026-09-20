"""The one text a mobile notification carries. Moved unchanged from app/mobile_alerts.py.

A transport sends these words and nothing else, so it can import them without importing the routes. They name
no trade, symbol, price, wallet or amount: a lock screen shows them.
"""


def message(kind, event_id):
    if kind not in ('test', 'attention'):
        raise ValueError('Unsupported notification template')
    return ('TradeSync notification test.' if kind == 'test' else 'TradeSync needs attention. Open your dashboard.') + ' Reference ' + str(event_id)[:8]
