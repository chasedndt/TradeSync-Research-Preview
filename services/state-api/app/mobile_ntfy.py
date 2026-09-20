"""Publishing one generic message to ntfy.sh. Moved unchanged from app/mobile_alerts.py.

ntfy.sh is fixed, HTTPS only, and the topic must be one TradeSync generated, so no caller controls a URL.
An accepted provider message is NOT proof that a phone received it.
"""
import re

import httpx

from app.mobile_message import message


async def publish(topic, kind, event_id):
    if not re.fullmatch(r'tradesync-[a-f0-9]{48}', topic):
        raise ValueError('Invalid generated topic')
    body = message(kind, event_id)
    async with httpx.AsyncClient(timeout=8, trust_env=False, follow_redirects=False) as client:
        response = await client.post('https://ntfy.sh/'+topic, content=body,
                                     headers={'Title': 'TradeSync', 'Priority': 'default', 'Content-Type': 'text/plain'})
        response.raise_for_status()
        payload = response.json()
    if (not isinstance(payload, dict) or payload.get('event') != 'message'
            or payload.get('topic') != topic or payload.get('message') != body
            or not isinstance(payload.get('id'), str) or not payload['id']):
        raise ValueError('Provider acceptance could not be verified')
    return payload['id']
