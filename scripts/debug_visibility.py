"""Debug script to check why favourite cards might be hidden."""
import re
from bs4 import BeautifulSoup

html = open("output/reports/report_2026-03-23.html", encoding="utf-8").read()
soup = BeautifulSoup(html, "html.parser")

# Check sec-favourites section
fav_section = soup.find(id="sec-favourites")
if fav_section:
    print(f"Tag: {fav_section.name}")
    print(f"Has 'open' attr: {fav_section.has_attr('open')}")

    fav_cards_div = fav_section.find(id="fav-cards")
    cards = fav_cards_div.find_all(class_="property-card") if fav_cards_div else []
    print(f"Cards in fav-cards: {len(cards)}")
    for card in cards:
        style = card.get("style", "")
        card_id = card.get("id", "no-id")
        addr = card.get("data-address", "?")
        print(f"  {card_id}: style='{style}' addr={addr[:40]}")
else:
    print("sec-favourites NOT FOUND")

# Check all sections for property-card counts
print("\n--- Section card counts ---")
for details in soup.find_all("details"):
    section_id = details.get("id", "?")
    cards_in = details.find_all(class_="property-card")
    has_open = details.has_attr("open")
    print(f"  {section_id}: {len(cards_in)} cards, open={has_open}")

# Check CSS for property-card hiding rules
print("\n--- CSS rules affecting property-card ---")
styles = soup.find_all("style")
for i, st in enumerate(styles):
    text = st.string or ""
    for match in re.finditer(r"[^}]*\.property-card[^{]*\{[^}]*\}", text):
        snippet = match.group()
        if "display" in snippet or "visibility" in snippet or "height: 0" in snippet:
            print(f"  Style block {i}: {snippet[:300]}")

# Check if data-area is set on favourite cards
print("\n--- Favourite card data attributes ---")
if fav_section:
    fav_cards_div = fav_section.find(id="fav-cards")
    if fav_cards_div:
        for card in fav_cards_div.find_all(class_="property-card"):
            card_id = card.get("id", "?")
            area = card.get("data-area", "MISSING")
            score = card.get("data-score", "?")
            price = card.get("data-price", "?")
            print(f"  {card_id}: area={area} score={score} price={price}")
