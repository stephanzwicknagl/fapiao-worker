"""Category definitions for VAT reimbursement forms.

Maps English category names (used in form dropdowns) to Chinese translations
(used for AI prompt context to improve categorization accuracy).
"""

# English category name -> Chinese translation
# Extracted from "VAT Reimbursement Claim Form - July 2026 - update.xlsx"
# Column M (English) -> Column N (automatic translate/Chinese)
CATEGORY_NAMES: dict[str, str] = {
    "Accommodation / Lodging": "住宿费",
    "Audio / Video Equipment": "影音设备",
    "Auto Parts": "汽车配件",
    "Automobile": "汽车",
    "Bag / Purse": "包",
    "Beer/Wine": "酒",
    "Beauty & Hairdressing": "美容美发",
    "Bicycle": "自行车",
    "Bicycle Parts": "自行车配件",
    "Book / Newspaper": "书报杂志",
    "Camera": "照相机",
    "Carpet": "地毯",
    "Ceramics": "陶瓷",
    "Cleaning Service": "清洁服务费",
    "Clothes": "服装",
    "Computer": "电脑",
    "Computer Accessories": "电脑配件",
    "Consulting Fee": "咨询费",
    "Cosmetics": "化妆品",
    "Cultural Service (Entry tickets for tourist attractions)": "文化旅游服务费",
    "DVD / CD": "音像制品",
    "Eyeglasses": "眼镜",
    "Fitness fee": "健身费",
    "Flowers / Plants": "花卉/绿植",
    "Fruits": "水果",
    "Furniture": "家具",
    "Gasoline": "汽油",
    "Groceries": "食品",
    "Handicrafts": "工艺品",
    "Health care fee": "医疗服务费",
    "Home Decorations": "装饰品",
    "Household Electrical Appliances": "家用电器",
    "Household Items": "日用品",
    "Jewelry": "珠宝首饰",
    "Laundry fee": "洗衣费",
    "Maintenance Service Parts": "维修费",
    "Medicine": "药品",
    "Mobile Phone": "手机",
    "Mobile Phone Accessories": "手机配件",
    "Motor vehicle insurance": "机动车保险费",
    "Musical Instruments": "乐器",
    "Office Supplies": "办公用品",
    "Other": "其他",
    "Paint / Paint Supplies": "漆",
    "Pet medical fees": "宠物诊疗费",
    "Pet Supplies": "宠物用品",
    "Picture": "画",
    "Picture Frames": "画框",
    "Property Service": "物业服务费",
    "Restaurant": "餐费",
    "Scooter": "电动自行车",
    "Shoes": "鞋",
    "Sporting Goods": "体育用品",
    "Tea": "茶叶",
    "Toys": "玩具",
    "Transportation fee": "交通费",
    "Tuition Fee": "学费",
    "TV": "电视",
    "Watch": "手表",
    "Wellness & Livelihood (Spa, Massages, Acupuncture, etc.)": "保健费",
}

# English category names only (for form dropdown validation)
CATEGORY_ENGLISH_NAMES: list[str] = list(CATEGORY_NAMES.keys())

# Chinese category names only (for reference)
CATEGORY_CHINESE_NAMES: list[str] = [name for name in CATEGORY_NAMES.values() if name]


def get_categories_for_ai_prompt() -> list[tuple[str, str]]:
    """Return categories as (english, chinese) tuples for AI system prompt.

    The AI uses both English and Chinese context to better categorize vendors
    based on Chinese vendor names and product descriptions, while outputting
    English category names for form compatibility.
    """
    return list(CATEGORY_NAMES.items())


def get_english_category(chinese_name: str) -> str | None:
    """Lookup English category name by Chinese translation."""
    for eng, chn in CATEGORY_NAMES.items():
        if chn == chinese_name:
            return eng
    return None


def get_chinese_category(english_name: str) -> str | None:
    """Lookup Chinese translation by English category name."""
    return CATEGORY_NAMES.get(english_name)
