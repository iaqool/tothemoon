import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# Используем быструю и недорогую модель Flash
MODEL_NAME = "gemini-2.5-flash"


def generate_icebreaker(
    name: str,
    chain: str,
    mcap: float = 0,
    contact_name: str = "",
    is_upcoming: bool = False,
    launchpad: str = "",
) -> str:
    """
    Генерирует персонализированное первое предложение для email на английском.
    """
    if not GEMINI_API_KEY:
        # Fallback если нет ключа
        greeting = f"Hey {contact_name}," if contact_name else "Hey,"
        if is_upcoming:
            return f"{greeting} I saw {name} is preparing for an upcoming token launch and thought it made sense to connect early."
        return f"{greeting} I've been following {name} recently and I'm really impressed by your progress."

    greeting = f"Hi {contact_name}," if contact_name else "Hi,"
    mcap_formatted = (
        f"${mcap / 1e6:.1f}M"
        if mcap >= 1e6
        else f"${mcap / 1e3:.1f}K"
        if mcap >= 1e3
        else str(mcap)
    )

    # Промпт с учетом блокчейна (тон)
    launch_context = (
        f"The project is preparing for an upcoming token sale{f' on {launchpad}' if launchpad else ''}. Focus on launch readiness, liquidity from day one, and pre-listing coordination."
        if is_upcoming
        else "The project is already live. Focus on current traction and market momentum."
    )

    prompt = f"""
    You are a professional Business Development Manager at 'Tothemoon', a crypto exchange listing agency.
    Write exactly ONE engaging, personalized opening sentence for a cold email to the team of a crypto project.
    
    Project Name: {name}
    Blockchain: {chain}
    Market Cap: {mcap_formatted}
    Context: {launch_context}
    
    Rules:
    1. Start with '{greeting}'
    2. Write exactly ONE sentence after the greeting.
    3. Be natural, not overly salesy. Mention their recent launch or growth.
    4. Tone guidelines: If blockchain is 'Solana' or 'TON' or 'Base' (often memecoins or hype projects), use a slightly more energetic/informal tone (you can use one emoji like 🚀 or 🔥). If it is 'Ethereum', 'Arbitrum' or others, use a formal, professional tone.
    5. Do not include subject lines, sign-offs, or any other text.
    
    Output example:
    {greeting} I saw {name}'s recent momentum on {chain} and was really impressed by the trading volume you're building!
    """

    try:
        model = genai.GenerativeModel(MODEL_NAME)
        response = model.generate_content(prompt)
        text = response.text.strip()
        # Убираем возможные кавычки в начале и конце
        if text.startswith('"') and text.endswith('"'):
            text = text[1:-1]
        return text
    except Exception as e:
        print(f"[WARN] Gemini API Error: {e}")
        # Fallback
        if is_upcoming:
            return f"{greeting} I saw {name} is gearing up for launch and thought it was the right moment to discuss liquidity and listing support early."
        return f"{greeting} I've been tracking {name}'s recent growth on {chain} and am really impressed by what your team is building."


if __name__ == "__main__":
    # Тест
    print(generate_icebreaker("DogeMoon", "Solana", 5000000, "Alex"))
    print(generate_icebreaker("DeFiLend", "Ethereum", 15000000))
