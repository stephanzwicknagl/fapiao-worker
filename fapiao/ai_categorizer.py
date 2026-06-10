"""AI-powered vendor categorization using the OpenAI SDK."""

import asyncio
import logging
import os
import re

from openai import APIError, AsyncOpenAI

logger = logging.getLogger(__name__)

# Maximum number of sellers to categorize in a single batch request
DEFAULT_BATCH_SIZE = 10

# Maximum total load on the API (batch_size * max_concurrency should be < 40)
DEFAULT_MAX_CONCURRENCY = 5


def _build_system_prompt(categories: list[str]) -> str:
    """Build the system prompt with categories (constant part)."""
    categories_list = "\n".join(f"  - {cat}" for cat in categories)
    return f"""Categorize Chinese vendors for VAT forms. Use EXACTLY one category per vendor:

{categories_list}

Rules:
- Pick the dominant category based on tax codes and products
- Respond ONLY as: vendor_name = "Category"
- Use "Other" if uncertain
- No explanations, no markdown
"""


#     return f"""You are a specialized assistant for categorizing Chinese vendors for VAT reimbursement forms.
#
# Your task is to assign each vendor to exactly ONE category from the following list based on their sold products:
#
# {categories_list}
#
# RULES:
# 1. Analyze the vendor's product list (tax categories and product names in Chinese).
# 2. Select the SINGLE most appropriate category for the vendor overall.
# 3. If a vendor sells diverse products, pick the dominant category based on:
#    - Product types and descriptions
#    - Tax classification codes (e.g., 餐饮服务=Restaurant, 医疗仪器器械=Medicine/Health care)
# 4. Respond ONLY in TOML format: vendor_name = "Category"
# 5. Use the exact vendor name as provided (preserve Chinese characters).
# 6. Use the exact category name as shown above (case-sensitive).
# 7. If uncertain or products span multiple unrelated categories, use "Other".
# 8. Do not add explanations, comments, or markdown formatting.
#
# Example response:
# ```
# 杭州芙茂电子商务有限公司 = "Furniture"
# 江苏鱼跃电子科技有限公司 = "Medicine"
# 武汉沃歌斯餐饮有限公司 = "Restaurant"
# ```"""


def _build_user_prompt(sellers: set[str], seller_products: dict[str, list[tuple[str, str]]] | None = None) -> str:
    """Build the user prompt with seller names and their products."""
    lines = ["Categorize the following vendors based on their products:\n"]

    for seller in sellers:
        lines.append(f"\nVendor: {seller}")
        products = seller_products.get(seller, []) if seller_products else []
        if products:
            lines.append("Products:")
            for tax_cat, prod_name in products:
                lines.append(f"  - *{tax_cat}*{prod_name}")
        else:
            lines.append("Products: (not available)")

    lines.append('\nRespond in TOML format (vendor = "Category") for each vendor above.')
    return "\n".join(lines)


def _parse_toml_response(content: str, sellers: set[str], categories: list[str]) -> dict[str, str]:
    """
    Parse TOML-like response from AI.

    Expected format: vendor_name = "Category"
    Handles Chinese vendor names and quoted values.
    """
    successful = {}
    categories_lower = {cat.lower(): cat for cat in categories}
    sellers_normalized = {seller.strip(): seller for seller in sellers}

    # Remove code blocks if present
    content = re.sub(r"^```\w*\n?", "", content, flags=re.MULTILINE)
    content = re.sub(r"\n?```$", "", content, flags=re.MULTILINE)

    for line in content.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Match pattern: key = "value" or key = 'value' or key = value
        # Handle Chinese characters in keys
        match = re.match(r'^([\w\s\u4e00-\u9fff]+?)\s*=\s*["\']?([^"\'#\n]+)["\']?$', line)
        if not match:
            logger.debug("Could not parse line: %s", line)
            continue

        seller_key = match.group(1).strip()
        category_raw = match.group(2).strip()

        # Find the original seller name (handle slight variations)
        seller_name = None
        if seller_key in sellers_normalized:
            seller_name = sellers_normalized[seller_key]
        else:
            # Try case-insensitive match
            for norm, orig in sellers_normalized.items():
                if norm.lower() == seller_key.lower():
                    seller_name = orig
                    break

        if not seller_name:
            logger.debug("Parsed seller '%s' not in expected sellers list", seller_key)
            continue

        # Validate and normalize category
        category_lower = category_raw.lower()
        if category_lower in categories_lower:
            successful[seller_name] = categories_lower[category_lower]
        elif category_lower in ("other", "unknown", "uncertain", "not sure", "n/a", "none"):
            logger.debug("AI marked seller '%s' as uncertain: %s", seller_name, category_raw)
        else:
            # Try substring match
            matched = False
            for cat_lower, cat_orig in categories_lower.items():
                if cat_lower in category_lower or category_lower in cat_lower:
                    successful[seller_name] = cat_orig
                    matched = True
                    logger.debug("Matched category '%s' for seller '%s' via substring", cat_orig, seller_name)
                    break
            if not matched:
                logger.warning("Unrecognized category for seller '%s': %s", seller_name, category_raw)

    return successful


def _create_client() -> AsyncOpenAI | None:
    """Create async OpenAI client if credentials are configured."""
    api_url = os.environ.get("AI_API_URL")
    api_key = os.environ.get("AI_API_KEY")

    if not api_url or not api_key:
        logger.debug("AI categorization not configured (AI_API_URL or AI_API_KEY missing)")
        return None

    return AsyncOpenAI(api_key=api_key, base_url=api_url)


async def _categorize_single_batch(
    client: AsyncOpenAI,
    model: str,
    system_prompt: str,
    batch: set[str],
    seller_products: dict[str, list[tuple[str, str]]] | None,
    categories: list[str],
    semaphore: asyncio.Semaphore,
    batch_index: int,
) -> tuple[dict[str, str], set[str]]:
    """
    Process a single batch with semaphore-controlled concurrency.

    Returns:
        Tuple of (successful_mappings, still_unmapped) for this batch
    """
    async with semaphore:
        user_prompt = _build_user_prompt(batch, seller_products)

        try:
            completion = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=1,
                max_tokens=50 * len(batch),
                reasoning_effort="low",
            )

            # Debug logging
            logger.debug("AI API batch response (batch %d): %s", batch_index, completion)

            # Extract and parse response
            if not completion.choices:
                logger.warning("AI API returned no choices for batch %d", batch_index)
                return {}, batch

            message = completion.choices[0].message
            if message.content is None:
                logger.warning("AI API returned None content for batch %d", batch_index)
                return {}, batch

            content = message.content.strip()
            if not content:
                logger.warning("AI API returned empty content for batch %d", batch_index)
                return {}, batch

            # Parse TOML response
            batch_results = _parse_toml_response(content, batch, categories)

            # Track unmapped sellers from this batch
            batch_unmapped = {seller for seller in batch if seller not in batch_results}

            return batch_results, batch_unmapped

        except APIError as e:
            logger.error("AI API error for batch %d: %s", batch_index, e)
            return {}, batch
        except Exception:
            logger.exception("Unexpected error during AI categorization for batch %d", batch_index)
            return {}, batch


def categorize_sellers_batch(
    sellers: set[str],
    categories: list[str],
    seller_products: dict[str, list[tuple[str, str]]] | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
) -> tuple[dict[str, str], set[str]]:
    """
    Categorize multiple vendors using parallel async AI API requests.

    Args:
        sellers: Set of vendor names to categorize
        categories: List of valid category options
        seller_products: Optional dict mapping seller name to list of (tax_category, product_name) tuples
        batch_size: Number of sellers to process per API request
        max_concurrency: Maximum number of concurrent API requests

    Returns:
        Tuple of (successful_mappings, still_unmapped)
        - successful_mappings: dict mapping seller name to category
        - still_unmapped: set of sellers that couldn't be categorized

    Raises:
        ValueError: If batch_size + max_concurrency >= 40
    """
    # Validate total load constraint
    if batch_size + max_concurrency >= 40:
        raise ValueError(f"batch_size ({batch_size}) + max_concurrency ({max_concurrency}) must be < 40")

    client = _create_client()
    if not client:
        return {}, sellers

    model = "moonshot-v1-8k"
    system_prompt = _build_system_prompt(categories)

    # Prepare batches
    sellers_list = list(sellers)
    batches: list[set[str]] = [set(sellers_list[i : i + batch_size]) for i in range(0, len(sellers_list), batch_size)]

    async def run_all_batches() -> tuple[dict[str, str], set[str]]:
        semaphore = asyncio.Semaphore(max_concurrency)

        # Create all batch tasks
        tasks = [
            _categorize_single_batch(
                client=client,
                model=model,
                system_prompt=system_prompt,
                batch=batch,
                seller_products=seller_products,
                categories=categories,
                semaphore=semaphore,
                batch_index=i,
            )
            for i, batch in enumerate(batches)
        ]

        # Run all batches concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Aggregate results
        successful: dict[str, str] = {}
        still_unmapped: set[str] = set()

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error("Batch %d failed with exception: %s", i, result)
                still_unmapped.update(batches[i])
            else:
                batch_successful, batch_unmapped = result
                successful.update(batch_successful)
                still_unmapped.update(batch_unmapped)

        return successful, still_unmapped

    # Run async event loop
    successful, still_unmapped = asyncio.run(run_all_batches())

    if successful:
        logger.info("AI categorized %d/%d sellers", len(successful), len(sellers))
    if still_unmapped:
        logger.debug("AI could not categorize %d sellers: %s", len(still_unmapped), still_unmapped)

    return successful, still_unmapped


def categorize_seller(
    seller_name: str,
    categories: list[str],
    seller_products: dict[str, list[tuple[str, str]]] | None = None,
) -> str | None:
    """
    Categorize a single vendor using AI API.

    Args:
        seller_name: The vendor name from the fapiao
        categories: List of valid category options
        seller_products: Optional dict mapping seller name to list of (tax_category, product_name) tuples

    Returns:
        Selected category name, or None if uncertain/failed
    """
    successful, unmapped = categorize_sellers_batch({seller_name}, categories, seller_products, batch_size=1)
    return successful.get(seller_name)


def categorize_sellers(
    sellers: set[str],
    categories: list[str],
    seller_products: dict[str, list[tuple[str, str]]] | None = None,
) -> tuple[dict[str, str], set[str]]:
    """
    Categorize multiple vendors using AI API.

    Args:
        sellers: Set of vendor names to categorize
        categories: List of valid category options
        seller_products: Optional dict mapping seller name to list of (tax_category, product_name) tuples

    Returns:
        Tuple of (successful_mappings, still_unmapped)
        - successful_mappings: dict mapping seller name to category
        - still_unmapped: set of sellers that couldn't be categorized
    """
    return categorize_sellers_batch(sellers, categories, seller_products)
