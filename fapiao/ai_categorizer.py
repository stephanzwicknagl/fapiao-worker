"""AI-powered vendor categorization using the OpenAI SDK."""

import logging
import os

from openai import APIError, OpenAI

logger = logging.getLogger(__name__)


def _build_prompt(seller_name: str, categories: list[str]) -> str:
    """Build the categorization prompt for the AI."""
    categories_list = "\n".join(f"- {cat}" for cat in categories)
    return f"""You are categorizing Chinese vendors for VAT reimbursement forms.

Vendor name: "{seller_name}"

Available categories:
{categories_list}

Based on the vendor name, select the SINGLE most appropriate category from the list above.
Respond with ONLY the category name, exactly as shown.
If uncertain or the vendor doesn't match any category, respond with "Other".

Category:"""


def categorize_seller(seller_name: str, categories: list[str]) -> str | None:
    """
    Categorize a vendor using AI API.

    Args:
        seller_name: The vendor name from the fapiao
        categories: List of valid category options

    Returns:
        Selected category name, or None if uncertain/failed
    """
    api_url = os.environ.get("AI_API_URL")
    api_key = os.environ.get("AI_API_KEY")
    model = os.environ.get("AI_MODEL", "gpt-4o-mini")

    if not api_url or not api_key:
        logger.debug("AI categorization not configured (AI_API_URL or AI_API_KEY missing)")
        return None

    client = OpenAI(
        api_key=api_key,
        base_url=api_url,
    )

    prompt = _build_prompt(seller_name, categories)

    try:
        completion = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=1,
            max_tokens=100,
        )

        # Debug logging
        logger.debug("AI API response for seller '%s': %s", seller_name, completion)

        # Extract the response content safely
        if not completion.choices:
            logger.warning("AI API returned no choices for seller: %s", seller_name)
            return None

        message = completion.choices[0].message
        if message.content is None:
            logger.warning("AI API returned None content for seller: %s", seller_name)
            return None

        content = message.content.strip()

        if not content:
            logger.warning("AI API returned empty content for seller: %s", seller_name)
            return None

        # Check for uncertainty indicators
        lower_content = content.lower()
        if lower_content in ("other", "unknown", "uncertain", "not sure", "n/a", "none"):
            logger.debug("AI indicated uncertainty for seller '%s': %s", seller_name, content)
            return None

        # Validate against allowed categories (case-insensitive)
        categories_lower = {cat.lower(): cat for cat in categories}
        if lower_content in categories_lower:
            return categories_lower[lower_content]

        # Try exact match (in case of whitespace differences)
        for cat in categories:
            if content == cat:
                return cat

        # Try substring matching (AI might add extra text)
        for cat in categories:
            if cat.lower() in lower_content:
                logger.debug("Matched category '%s' for seller '%s' via substring", cat, seller_name)
                return cat

        logger.warning(
            "AI returned unrecognized category for seller '%s': %s (not in allowed categories)",
            seller_name,
            content,
        )
        return None

    except APIError as e:
        logger.error("AI API error for seller '%s': %s", seller_name, e)
        return None
    except Exception:
        logger.exception("Unexpected error during AI categorization for seller '%s'", seller_name)
        return None


def categorize_sellers(sellers: set[str], categories: list[str]) -> tuple[dict[str, str], set[str]]:
    """
    Categorize multiple vendors using AI API.

    Args:
        sellers: Set of vendor names to categorize
        categories: List of valid category options

    Returns:
        Tuple of (successful_mappings, still_unmapped)
        - successful_mappings: dict mapping seller name to category
        - still_unmapped: set of sellers that couldn't be categorized
    """
    successful = {}
    still_unmapped = set()

    for seller in sellers:
        category = categorize_seller(seller, categories)
        if category:
            successful[seller] = category
        else:
            still_unmapped.add(seller)

    if successful:
        logger.info("AI categorized %d/%d sellers", len(successful), len(sellers))
    if still_unmapped:
        logger.debug("AI could not categorize %d sellers: %s", len(still_unmapped), still_unmapped)

    return successful, still_unmapped
