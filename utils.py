import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from difflib import SequenceMatcher
import re

# CalorieNinjas API key (replace with your own)
CALORIE_NINJAS_API_KEY = "+VR0UYEcTTcqy/Fc5z9Veg==3nYhsDT1hav4l9O4"

# Setup requests session with retries
session = requests.Session()
retry = Retry(total=3, backoff_factor=0.3, status_forcelist=[500, 502, 503, 504])
adapter = HTTPAdapter(max_retries=retry)
session.mount("https://", adapter)
session.mount("http://", adapter)

def similar(a, b):
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

def normalize_text(text):
    text = text.lower()
    text = re.sub(r'[^a-z0-9 ]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def search_calorieninjas_food(name):
    url = "https://api.calorieninjas.com/v1/nutrition"
    headers = {"X-Api-Key": CALORIE_NINJAS_API_KEY}
    params = {"query": name}
    try:
        response = session.get(url, headers=headers, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()
        items = data.get("items", [])
        if not items:
            return None
        # Pick the best match (highest similarity)
        normalized_query = normalize_text(name)
        best_item = None
        best_score = 0
        for item in items:
            desc = normalize_text(item.get("name", ""))
            score = similar(desc, normalized_query)
            if score > best_score:
                best_score = score
                best_item = item
        if best_item:
            return {
                "source": "CalorieNinjas",
                "name": best_item.get("name", name).title(),
                "calories_per_100g": round(best_item.get("calories", 0), 2),
                "protein": round(best_item.get("protein_g", 0), 2),
                "carbs": round(best_item.get("carbohydrates_total_g", 0), 2),
                "fats": round(best_item.get("fat_total_g", 0), 2),
            }
        return None
    except requests.RequestException:
        return None

def extract_nutrient(food, nutrient_name, unit=None):
    for nutrient in food.get("foodNutrients", []):
        if nutrient.get("nutrientName") == nutrient_name:
            val = nutrient.get("value", 0)
            nutrient_unit = nutrient.get("unitName", "").upper()
            if unit is None or nutrient_unit == unit:
                return val
            if unit == "KCAL" and nutrient_unit == "KJ":
                return val * 0.239006
    return 0

def search_usda_food(name):
    api_key = "E9Czl3jcRno6unLhGvOSkkZkPbbE8Q5jRCRoKnvS"
    search_url = "https://api.nal.usda.gov/fdc/v1/foods/search"
    params = {
        "query": name,
        "pageSize": 25,
        "dataType": ["Foundation", "SR Legacy", "Branded"],
        "api_key": api_key
    }
    try:
        response = session.get(search_url, params=params, timeout=5)
        response.raise_for_status()
    except requests.RequestException:
        return None

    foods = response.json().get("foods", [])
    if not foods:
        return None

    normalized_query = normalize_text(name)
    best_food = None
    best_score = 0

    for food in foods:
        desc = normalize_text(food.get("description", ""))
        brand = normalize_text(food.get("brandOwner", ""))
        combined = f"{desc} {brand}".strip()
        score = similar(combined, normalized_query)

        # Bonus for Foundation or SR Legacy data types
        if food.get("dataType") in ["Foundation", "SR Legacy"]:
            score += 0.1

        calories = extract_nutrient(food, "Energy", "KCAL")
        if calories < 20:  # filter out unlikely foods
            continue

        if score > best_score:
            best_score = score
            best_food = food

    if best_food:
        try:
            fdc_id = best_food["fdcId"]
            detail_url = f"https://api.nal.usda.gov/fdc/v1/food/{fdc_id}"
            detail_resp = session.get(detail_url, params={"api_key": api_key}, timeout=5)
            detail_resp.raise_for_status()
            detailed_food = detail_resp.json()

            return {
                "source": "USDA",
                "name": best_food.get("description", name).title(),
                "calories_per_100g": round(extract_nutrient(detailed_food, "Energy", "KCAL"), 2),
                "protein": round(extract_nutrient(detailed_food, "Protein", "G"), 2),
                "carbs": round(extract_nutrient(detailed_food, "Carbohydrate, by difference", "G"), 2),
                "fats": round(extract_nutrient(detailed_food, "Total lipid (fat)", "G"), 2)
            }
        except Exception:
            return {
                "source": "USDA",
                "name": best_food.get("description", name).title(),
                "calories_per_100g": round(extract_nutrient(best_food, "Energy", "KCAL"), 2),
                "protein": round(extract_nutrient(best_food, "Protein", "G"), 2),
                "carbs": round(extract_nutrient(best_food, "Carbohydrate, by difference", "G"), 2),
                "fats": round(extract_nutrient(best_food, "Total lipid (fat)", "G"), 2)
            }

    return None

def search_food(name):
    url = "https://world.openfoodfacts.org/cgi/search.pl"
    params = {
        "search_terms": name,
        "search_simple": 1,
        "action": "process",
        "json": 1
    }
    try:
        response = session.get(url, params=params, timeout=5)
        response.raise_for_status()
    except requests.RequestException:
        return None

    data = response.json()
    if data.get("count", 0) > 0:
        product = data["products"][0]
        nutriments = product.get("nutriments", {})

        def get_nutrient(key):
            val = nutriments.get(key)
            try:
                return round(float(val), 2) if val is not None else 0
            except (ValueError, TypeError):
                return 0

        return {
            "source": "OpenFoodFacts",
            "name": product.get("product_name", name),
            "calories_per_100g": get_nutrient("energy-kcal_100g"),
            "protein": get_nutrient("proteins_100g"),
            "carbs": get_nutrient("carbohydrates_100g"),
            "fats": get_nutrient("fat_100g")
        }
    return None

def smart_search(name):
    """Try CalorieNinjas first, then USDA, then fallback to OpenFoodFacts."""
    data = search_calorieninjas_food(name)
    if not data:
        data = search_usda_food(name)
    if not data:
        data = search_food(name)
    return data
