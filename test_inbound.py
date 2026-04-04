import requests
import json

# Для тестирования развернутого на Vercel замените localhost на ваш домен
WEBHOOK_URL = "http://localhost:3000/api/inbound" 
SECRET = "test_secret_123"

# Имитация пейлоада от Resend
payload = {
    "type": "email.inbound",
    "data": {
        "from": "Founder CEO <founder@example-crypto-project.com>",
        "to": ["reply@reply.tothemoon.agency"],
        "subject": "Re: Pre-Launch Listing Support",
        "text": "Hey there! Thanks for reaching out. Yes, we are planning our TGE in 2 weeks. Let's hop on a call tomorrow at 2 PM UTC. Sounds good?",
        "html": "<p>Hey there! Thanks for reaching out. Yes, we are planning our TGE in 2 weeks. Let's hop on a call tomorrow at 2 PM UTC. Sounds good?</p>"
    }
}

headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {SECRET}"
}

try:
    print(f"Sending MOCK Inbound Webhook to {WEBHOOK_URL}...")
    response = requests.post(WEBHOOK_URL, json=payload, headers=headers)
    print(f"Response Status: {response.status_code}")
    print(f"Response Body: {response.text}")
except requests.exceptions.ConnectionError:
    print(f"Failed to connect to {WEBHOOK_URL}. Is your local server running?")
