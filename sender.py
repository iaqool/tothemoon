import os
import re
import html as html_module
import resend
from dotenv import load_dotenv

load_dotenv()

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")

if RESEND_API_KEY:
    resend.api_key = RESEND_API_KEY

SENDER_EMAIL = (
    "hello@tothemoon.agency"  # Замените на ваш верифицированный домен в Resend
)


def sanitize_for_html(text: str) -> str:
    """Escape text for safe HTML embedding."""
    return html_module.escape(str(text)) if text else ""


def sanitize_for_text(text: str) -> str:
    """Strip potentially dangerous characters from plain text."""
    if not text:
        return ""
    return re.sub(r"[\r\n]+", " ", str(text)).strip()


def validate_email(email: str) -> bool:
    """Basic email format validation."""
    if not email or not isinstance(email, str):
        return False
    return bool(re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", email.strip()))


def send_email(
    to_email: str, subject: str, text_content: str, html_content: str = None
) -> dict:
    """
    Отправляет email через Resend API.
    """
    if not validate_email(to_email):
        print(f"[ERROR] Invalid email address: {to_email}")
        return None

    if not RESEND_API_KEY or RESEND_API_KEY == "your_resend_api_key_here":
        print(f"[MOCK SEND] To: {to_email} | Subject: {subject}")
        print(f"Content:\n{text_content}\n" + "-" * 40)
        return {"id": "mock_id_" + os.urandom(4).hex()}

    try:
        params = {
            "from": f"Tothemoon <{SENDER_EMAIL}>",
            "to": [to_email],
            "subject": subject,
            "text": text_content,
        }
        if html_content:
            params["html"] = html_content

        response = resend.Emails.send(params)
        return response
    except Exception as e:
        print(f"[ERROR] Failed to send email to {to_email}: {e}")
        return None


def build_stage1_email(icebreaker: str, name: str, ticker: str) -> dict:
    subject = f"CEX Listing & Market Making for {name} ({ticker})"

    text = f"""{icebreaker}

We specialize in helping projects like {name} maximize visibility across Tier-1/2 CEXs and build sustained liquidity (spread < 1%, volume > $10k). We have a database of 2M+ users and are a Top-30 agency globally.

Also, we provide free tools like Listagram bot for automated listing tracking to help your community stay engaged.

Would love to have a quick 10-min call this week — are you open to it?

Best,
The Tothemoon Team
https://tothemoon.agency
"""

    safe_icebreaker = sanitize_for_html(icebreaker)
    safe_name = sanitize_for_html(name)

    html = f"""<p>{safe_icebreaker}</p>
<p>We specialize in helping projects like <strong>{safe_name}</strong> maximize visibility across Tier-1/2 CEXs and build sustained liquidity (spread &lt; 1%, volume &gt; $10k). We have a database of 2M+ users and are a Top-30 agency globally.</p>
<p>Also, we provide free tools like Listagram bot for automated listing tracking to help your community stay engaged.</p>
<p>Would love to have a quick 10-min call this week — are you open to it?</p>
<p>Best,<br>The Tothemoon Team<br><a href="https://tothemoon.agency">tothemoon.agency</a></p>
"""
    return {"subject": subject, "text": text, "html": html}


def build_stage1_upcoming_email(
    icebreaker: str, name: str, ticker: str, launchpad: str = ""
) -> dict:
    subject = f"Pre-Launch Listing Support for {name} ({ticker})"
    launchpad_line = f" on {launchpad}" if launchpad else ""

    text = f"""{icebreaker}

We work with projects ahead of launch to make sure day-one trading does not break on liquidity. TTM gives teams direct access to 2M+ active traders, Top-30 exchange distribution, and clear MM standards from the first trading session.

Our baseline is spread < 1%, daily volume > $10k, and stable depth around the mid price. If your team still needs a lightweight MM setup, we can also support with Listagram{launchpad_line}.

If your sale timeline is already taking shape, happy to prepare a preliminary listing path before launch.

Best,
The Tothemoon Team
https://tothemoon.agency
"""

    safe_icebreaker = sanitize_for_html(icebreaker)
    safe_launchpad_line = sanitize_for_html(launchpad_line)

    html = f"""<p>{safe_icebreaker}</p>
<p>We work with projects ahead of launch to make sure day-one trading does not break on liquidity. TTM gives teams direct access to <strong>2M+</strong> active traders, Top-30 exchange distribution, and clear MM standards from the first trading session.</p>
<p>Our baseline is spread &lt; 1%, daily volume &gt; $10k, and stable depth around the mid price. If your team still needs a lightweight MM setup, we can also support with Listagram{safe_launchpad_line}.</p>
<p>If your sale timeline is already taking shape, happy to prepare a preliminary listing path before launch.</p>
<p>Best,<br>The Tothemoon Team<br><a href="https://tothemoon.agency">tothemoon.agency</a></p>
"""
    return {"subject": subject, "text": text, "html": html}


def build_followup1_email(name: str, ticker: str, contact_name: str = "") -> dict:
    subject = f"Re: CEX Listing & Market Making for {name} ({ticker})"
    greeting = f"Hi {contact_name}," if contact_name else "Hi,"

    text = f"""{greeting}

Just following up on my earlier note about {name} ({ticker}). 

Are you the right person to discuss exchange listings and liquidity strategies, or is there someone else on the team I should connect with?

We've recently helped similar projects gain real traction quickly. Happy to share a few case studies if you're curious!

Thanks,
The Tothemoon Team
"""
    return {"subject": subject, "text": text, "html": None}


def build_followup2_email(name: str, ticker: str, contact_name: str = "") -> dict:
    subject = f"Re: CEX Listing & Market Making for {name} ({ticker})"
    greeting = f"Hi {contact_name}," if contact_name else "Hi,"

    text = f"""{greeting}

Last note from my side — if the timing isn't right for {name} right now, totally understood.

Feel free to reach out whenever you're ready to explore exchange listing opportunities. Wishing you all the best with your roadmap! 🌙

Best,
The Tothemoon Team
"""
    return {"subject": subject, "text": text, "html": None}
