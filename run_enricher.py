"""
TTM Lead Gen - Manual Enricher Runner
Запускает сбор контактов для проектов в базе
"""

import enricher

if __name__ == "__main__":
    print("=" * 60)
    print("🔍 TTM ENRICHER - MANUAL RUN")
    print("=" * 60)
    print("\nНачинаем сбор контактов...")
    print("Режим: FULL (Email + X + Telegram + LinkedIn)")
    print("Лимит: 50 проектов")
    print("\nЭто займет ~2-3 часа (из-за rate-limit API)")
    print("Можно закрыть окно в любой момент - прогресс сохранится\n")

    # Запускаем enricher
    enricher.run(limit=50, email_only=False)

    print("\n" + "=" * 60)
    print("✅ ГОТОВО!")
    print("=" * 60)
    input("\nНажми Enter для выхода...")
