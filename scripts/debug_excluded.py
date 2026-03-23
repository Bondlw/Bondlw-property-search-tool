"""Check if favourite cards have excluded class or excl-active in generated HTML."""
from bs4 import BeautifulSoup

html = open("output/reports/report_2026-03-23.html", encoding="utf-8").read()
soup = BeautifulSoup(html, "html.parser")

fav_section = soup.find(id="sec-favourites")
if fav_section:
    fav_cards_div = fav_section.find(id="fav-cards")
    cards = fav_cards_div.find_all(class_="property-card") if fav_cards_div else []
    print(f"Cards in fav-cards: {len(cards)}\n")
    for card in cards:
        card_id = card.get("id", "?")
        classes = card.get("class", [])
        has_excluded = "excluded" in classes
        
        # Check for excl-active button
        buttons = card.find_all(class_="action-btn")
        has_excl_btn = any("excl-active" in (b.get("class") or []) for b in buttons)
        
        # Check the exclude button specifically (3rd action-btn)
        excl_btn_text = ""
        if len(buttons) >= 3:
            excl_btn_text = str(buttons[2])[:200]
        
        # Check data attributes
        area = card.get("data-area", "MISSING")
        score = card.get("data-score", "?")
        monthly = card.get("data-monthly", "?")
        
        print(f"{card_id}:")
        print(f"  classes: {classes}")
        print(f"  has 'excluded' class: {has_excluded}")
        print(f"  has 'excl-active' button: {has_excl_btn}")
        print(f"  area={area} score={score} monthly={monthly}")
        if has_excluded or has_excl_btn:
            print(f"  >>> EXCLUDE BUTTON: {excl_btn_text}")
        print()
else:
    print("sec-favourites NOT FOUND")
