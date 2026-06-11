"""Tests for AI categorizer module."""

import os
from unittest import mock
from unittest.mock import AsyncMock

from fapiao.ai_categorizer import (
    _build_system_prompt,
    _build_user_prompt,
    _create_client,
    _parse_toml_response,
    categorize_seller,
    categorize_sellers,
)

SAMPLE_CATEGORIES = ["Restaurant", "Medicine", "Groceries", "Other"]


class TestBuildSystemPrompt:
    """Tests for _build_system_prompt function."""

    def test_includes_all_categories(self):
        """Prompt should list all available categories."""
        prompt = _build_system_prompt(SAMPLE_CATEGORIES)
        for cat in SAMPLE_CATEGORIES:
            assert cat in prompt

    def test_includes_toml_format_instructions(self):
        """Prompt should specify TOML output format."""
        prompt = _build_system_prompt(SAMPLE_CATEGORIES)
        assert 'vendor_name = "Category"' in prompt

    def test_includes_product_analysis_rules(self):
        """Prompt should mention analyzing products and tax codes."""
        prompt = _build_system_prompt(SAMPLE_CATEGORIES)
        assert "product" in prompt
        assert "tax code" in prompt

    def test_includes_example_response(self):
        """Prompt should include example responses."""
        prompt = _build_system_prompt(SAMPLE_CATEGORIES)
        assert "杭州芙茂电子商务有限公司" in prompt
        assert "Furniture" in prompt or "Medicine" in prompt


class TestBuildUserPrompt:
    """Tests for _build_user_prompt function."""

    def test_includes_all_sellers(self):
        """Prompt should list all sellers to categorize."""
        sellers = {"沃尔玛", "滴滴出行"}
        prompt = _build_user_prompt(sellers)
        assert "沃尔玛" in prompt
        assert "滴滴出行" in prompt

    def test_shows_not_available_when_no_products(self):
        """When seller_products is None, should show 'not available'."""
        sellers = {"沃尔玛"}
        prompt = _build_user_prompt(sellers, None)
        assert "Products: (not available)" in prompt

    def test_shows_not_available_when_seller_has_no_products(self):
        """When seller has no products in dict, should show 'not available'."""
        sellers = {"沃尔玛"}
        prompt = _build_user_prompt(sellers, {"其他卖家": [("食品", "面包")]})
        assert "Products: (not available)" in prompt

    def test_includes_product_list_when_available(self):
        """Prompt should include tax category and product name."""
        sellers = {"武汉沃尔玛"}
        seller_products = {
            "武汉沃尔玛": [
                ("焙烤食品", "全麦面包"),
                ("日用杂品", "清洁剂"),
            ]
        }
        prompt = _build_user_prompt(sellers, seller_products)
        assert "焙烤食品" in prompt
        assert "全麦面包" in prompt
        assert "日用杂品" in prompt
        assert "清洁剂" in prompt
        assert "*焙烤食品*全麦面包" in prompt

    def test_multiple_sellers_with_products(self):
        """Prompt should handle multiple sellers with different product availability."""
        sellers = {"武汉沃尔玛", "神秘卖家"}
        seller_products = {
            "武汉沃尔玛": [("餐饮服务", "午餐")],
        }
        prompt = _build_user_prompt(sellers, seller_products)
        # First seller has products
        assert "武汉沃尔玛" in prompt
        assert "餐饮服务" in prompt
        # Second seller shows not available
        assert "神秘卖家" in prompt
        # Should have both product statuses
        assert prompt.count("Products:") >= 2


class TestParseTomlResponse:
    """Tests for _parse_toml_response function."""

    def test_parse_simple_response(self):
        """Parse a simple TOML response."""
        content = '沃尔玛 = "Groceries"'
        result = _parse_toml_response(content, {"沃尔玛"}, SAMPLE_CATEGORIES)
        assert result == {"沃尔玛": "Groceries"}

    def test_parse_multiple_vendors(self):
        """Parse response with multiple vendors."""
        content = """
沃尔玛 = "Groceries"
滴滴出行 = "Transportation fee"
"""
        result = _parse_toml_response(content, {"沃尔玛", "滴滴出行"}, ["Groceries", "Transportation fee"])
        assert result["沃尔玛"] == "Groceries"
        assert result["滴滴出行"] == "Transportation fee"

    def test_parse_with_code_blocks(self):
        """Parse response wrapped in code blocks."""
        content = """
```
沃尔玛 = "Groceries"
```
"""
        result = _parse_toml_response(content, {"沃尔玛"}, SAMPLE_CATEGORIES)
        assert result == {"沃尔玛": "Groceries"}

    def test_parse_with_chinese_vendor_names(self):
        """Parse response with Chinese vendor names."""
        content = '武汉沃尔玛电子商务有限公司 = "Groceries"'
        sellers = {"武汉沃尔玛电子商务有限公司"}
        result = _parse_toml_response(content, sellers, SAMPLE_CATEGORIES)
        assert result == {"武汉沃尔玛电子商务有限公司": "Groceries"}

    def test_case_insensitive_category_match(self):
        """Categories should match case-insensitively."""
        content = '沃尔玛 = "groceries"'
        result = _parse_toml_response(content, {"沃尔玛"}, ["Groceries"])
        assert result == {"沃尔玛": "Groceries"}

    def test_substring_category_match(self):
        """Should match categories via substring when exact match fails."""
        # "Groceries" is in "Groceries Store" (AI returns longer version)
        content = '沃尔玛 = "Groceries Store"'
        result = _parse_toml_response(content, {"沃尔玛"}, ["Groceries"])
        assert result == {"沃尔玛": "Groceries"}

    def test_substring_category_match_reverse(self):
        """Should match when category contains the AI response as substring."""
        # "Medicine" is in "Medical Equipment" would be the reverse case
        # Actually test: "Equip" should match "Equipment"
        content = '沃尔玛 = "Equipment"'
        result = _parse_toml_response(content, {"沃尔玛"}, ["Equip"])
        assert result == {"沃尔玛": "Equip"}

    def test_unknown_category_ignored(self):
        """Unknown categories should not be included in results."""
        content = '沃尔玛 = "UnknownCategory"'
        result = _parse_toml_response(content, {"沃尔玛"}, SAMPLE_CATEGORIES)
        assert result == {}

    def test_uncertain_categories_ignored(self):
        """Categories like 'other', 'unknown' should be ignored when not in valid list."""
        # Use categories without "Other" to test uncertain detection
        categories = ["Restaurant", "Medicine", "Groceries"]
        for uncertain in ["other", "unknown", "uncertain", "not sure", "n/a", "none"]:
            content = f'沃尔玛 = "{uncertain}"'
            result = _parse_toml_response(content, {"沃尔玛"}, categories)
            assert result == {}, f"Failed for {uncertain}"

    def test_seller_not_in_expected_list_ignored(self):
        """Sellers not in the expected set should be ignored."""
        content = '未知卖家 = "Groceries"'
        result = _parse_toml_response(content, {"沃尔玛"}, SAMPLE_CATEGORIES)
        assert result == {}

    def test_ignores_comments_and_empty_lines(self):
        """Should ignore comment lines and empty lines."""
        content = """
# This is a comment
沃尔玛 = "Groceries"

滴滴 = "Restaurant"
"""
        result = _parse_toml_response(content, {"沃尔玛", "滴滴"}, ["Groceries", "Restaurant"])
        assert len(result) == 2

    def test_single_quotes_accepted(self):
        """Should accept single-quoted values."""
        content = "沃尔玛 = 'Groceries'"
        result = _parse_toml_response(content, {"沃尔玛"}, SAMPLE_CATEGORIES)
        assert result == {"沃尔玛": "Groceries"}

    def test_unquoted_values_accepted(self):
        """Should accept unquoted values."""
        content = "沃尔玛 = Groceries"
        result = _parse_toml_response(content, {"沃尔玛"}, SAMPLE_CATEGORIES)
        assert result == {"沃尔玛": "Groceries"}


class TestCreateClient:
    """Tests for _create_client function."""

    def test_returns_none_when_env_vars_missing(self):
        """Should return None when API credentials are not configured."""
        with mock.patch.dict(os.environ, {}, clear=True):
            client = _create_client()
            assert client is None

    def test_returns_none_when_only_url_set(self):
        """Should return None when only URL is set."""
        with mock.patch.dict(os.environ, {"AI_API_URL": "https://api.example.com"}, clear=True):
            client = _create_client()
            assert client is None

    def test_returns_none_when_only_key_set(self):
        """Should return None when only key is set."""
        with mock.patch.dict(os.environ, {"AI_API_KEY": "secret"}, clear=True):
            client = _create_client()
            assert client is None

    def test_returns_client_when_both_set(self):
        """Should return OpenAI client when both env vars are set."""
        env = {
            "AI_API_URL": "https://api.example.com/v1",
            "AI_API_KEY": "test-key",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            client = _create_client()
            assert client is not None
            # Verify the client was configured correctly
            assert "api.example.com" in str(client.base_url)


class TestCategorizeSellersBatch:
    """Tests for categorize_sellers_batch function with mocked API."""

    @mock.patch("fapiao.ai_categorizer._create_client")
    def test_returns_empty_when_no_client(self, mock_create_client):
        """When API not configured, return empty mappings and all sellers unmapped."""
        mock_create_client.return_value = None
        sellers = {"沃尔玛", "滴滴"}
        result, unmapped = categorize_sellers(sellers, SAMPLE_CATEGORIES)
        assert result == {}
        assert unmapped == sellers

    @mock.patch("fapiao.ai_categorizer._create_client")
    def test_successful_categorization(self, mock_create_client):
        """Successfully categorize sellers via mocked API."""
        # Mock the OpenAI client
        mock_client = mock.MagicMock()
        mock_completion = mock.MagicMock()
        mock_completion.choices = [mock.MagicMock()]
        mock_completion.choices[0].message.content = '沃尔玛 = "Groceries"'
        mock_client.chat.completions.create = AsyncMock(return_value=mock_completion)
        mock_create_client.return_value = mock_client

        with mock.patch.dict(os.environ, {"MODEL": "gpt-4o-mini"}, clear=False):
            result, unmapped = categorize_sellers({"沃尔玛"}, SAMPLE_CATEGORIES)
            assert result == {"沃尔玛": "Groceries"}
            assert unmapped == set()

    @mock.patch("fapiao.ai_categorizer._create_client")
    def test_partial_categorization(self, mock_create_client):
        """When only some sellers are categorized, rest go to unmapped."""
        mock_client = mock.MagicMock()
        mock_completion = mock.MagicMock()
        mock_completion.choices = [mock.MagicMock()]
        # Only categorizes one of two sellers
        mock_completion.choices[0].message.content = '沃尔玛 = "Groceries"'
        mock_client.chat.completions.create = AsyncMock(return_value=mock_completion)
        mock_create_client.return_value = mock_client

        with mock.patch.dict(os.environ, {"MODEL": "gpt-4o-mini"}, clear=False):
            result, unmapped = categorize_sellers({"沃尔玛", "滴滴"}, SAMPLE_CATEGORIES)
            assert result == {"沃尔玛": "Groceries"}
            assert unmapped == {"滴滴"}

    @mock.patch("fapiao.ai_categorizer._create_client")
    def test_empty_response_treated_as_unmapped(self, mock_create_client):
        """Empty API response should mark all sellers as unmapped."""
        mock_client = mock.MagicMock()
        mock_completion = mock.MagicMock()
        mock_completion.choices = [mock.MagicMock()]
        mock_completion.choices[0].message.content = ""
        mock_client.chat.completions.create = AsyncMock(return_value=mock_completion)
        mock_create_client.return_value = mock_client

        sellers = {"沃尔玛"}
        with mock.patch.dict(os.environ, {"MODEL": "gpt-4o-mini"}, clear=False):
            result, unmapped = categorize_sellers(sellers, SAMPLE_CATEGORIES)
            assert result == {}
            assert unmapped == sellers

    @mock.patch("fapiao.ai_categorizer._create_client")
    def test_none_content_treated_as_unmapped(self, mock_create_client):
        """None content from API should mark all sellers as unmapped."""
        mock_client = mock.MagicMock()
        mock_completion = mock.MagicMock()
        mock_completion.choices = [mock.MagicMock()]
        mock_completion.choices[0].message.content = None
        mock_client.chat.completions.create = AsyncMock(return_value=mock_completion)
        mock_create_client.return_value = mock_client

        sellers = {"沃尔玛"}
        with mock.patch.dict(os.environ, {"MODEL": "gpt-4o-mini"}, clear=False):
            result, unmapped = categorize_sellers(sellers, SAMPLE_CATEGORIES)
            assert result == {}
            assert unmapped == sellers

    @mock.patch("fapiao.ai_categorizer._create_client")
    def test_no_choices_treated_as_unmapped(self, mock_create_client):
        """No choices in API response should mark all sellers as unmapped."""
        mock_client = mock.MagicMock()
        mock_completion = mock.MagicMock()
        mock_completion.choices = []
        mock_client.chat.completions.create = AsyncMock(return_value=mock_completion)
        mock_create_client.return_value = mock_client

        sellers = {"沃尔玛"}
        with mock.patch.dict(os.environ, {"MODEL": "gpt-4o-mini"}, clear=False):
            result, unmapped = categorize_sellers(sellers, SAMPLE_CATEGORIES)
            assert result == {}
            assert unmapped == sellers

    @mock.patch("fapiao.ai_categorizer._create_client")
    def test_api_error_treated_as_unmapped(self, mock_create_client):
        """API errors should mark all sellers as unmapped."""
        from openai import APIError

        mock_client = mock.MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=APIError(
                message="Rate limit exceeded",
                request=mock.MagicMock(),
                body=None,
            )
        )
        mock_create_client.return_value = mock_client

        sellers = {"沃尔玛"}
        with mock.patch.dict(os.environ, {"MODEL": "gpt-4o-mini"}, clear=False):
            result, unmapped = categorize_sellers(sellers, SAMPLE_CATEGORIES)
            assert result == {}
            assert unmapped == sellers

    @mock.patch("fapiao.ai_categorizer._create_client")
    def test_passes_seller_products_to_prompt(self, mock_create_client):
        """When seller_products provided, they should be included in API call."""
        mock_client = mock.MagicMock()
        mock_completion = mock.MagicMock()
        mock_completion.choices = [mock.MagicMock()]
        mock_completion.choices[0].message.content = '武汉沃尔玛 = "Groceries"'
        mock_client.chat.completions.create = AsyncMock(return_value=mock_completion)
        mock_create_client.return_value = mock_client

        seller_products = {"武汉沃尔玛": [("食品", "面包")]}
        with mock.patch.dict(os.environ, {"MODEL": "gpt-4o-mini"}, clear=False):
            categorize_sellers(
                {"武汉沃尔玛"},
                SAMPLE_CATEGORIES,
                seller_products=seller_products,
            )

        # Verify the API was called with products in the prompt
        call_args = mock_client.chat.completions.create.call_args
        messages = call_args.kwargs["messages"]
        user_message = messages[1]["content"]  # User message is second
        assert "食品" in user_message
        assert "面包" in user_message

    @mock.patch("fapiao.ai_categorizer._create_client")
    def test_batching_processes_sellers_in_batches(self, mock_create_client):
        """Should process sellers in batches of specified size."""
        mock_client = mock.MagicMock()
        mock_completion = mock.MagicMock()
        mock_completion.choices = [mock.MagicMock()]
        mock_completion.choices[0].message.content = '卖家1 = "Groceries"\n卖家2 = "Restaurant"'
        mock_client.chat.completions.create = AsyncMock(return_value=mock_completion)
        mock_create_client.return_value = mock_client

        sellers = {"卖家1", "卖家2", "卖家3", "卖家4"}
        with mock.patch.dict(os.environ, {"MODEL": "gpt-4o-mini"}, clear=False):
            categorize_sellers(sellers, SAMPLE_CATEGORIES, batch_size=2)

        # Should be called twice (4 sellers / batch_size 2)
        assert mock_client.chat.completions.create.call_count == 2


class TestCategorizeSeller:
    """Tests for categorize_seller function."""

    @mock.patch("fapiao.ai_categorizer.categorize_sellers")
    def test_calls_batch_with_single_seller(self, mock_categorize_sellers):
        """Should call batch function with single seller in set."""
        mock_categorize_sellers.return_value = ({"沃尔玛": "Groceries"}, set())
        result = categorize_seller("沃尔玛", SAMPLE_CATEGORIES)
        assert result == "Groceries"
        mock_categorize_sellers.assert_called_once()
        args = mock_categorize_sellers.call_args
        assert args.kwargs["batch_size"] == 1

    @mock.patch("fapiao.ai_categorizer.categorize_sellers")
    def test_passes_seller_products(self, mock_categorize_sellers):
        """Should pass seller_products to batch function."""
        mock_categorize_sellers.return_value = ({"沃尔玛": "Groceries"}, set())
        seller_products = {"沃尔玛": [("食品", "面包")]}
        categorize_seller("沃尔玛", SAMPLE_CATEGORIES, seller_products)
        args = mock_categorize_sellers.call_args
        # seller_products is passed as 3rd positional argument
        assert args.args[2] == seller_products

    @mock.patch("fapiao.ai_categorizer.categorize_sellers")
    def test_returns_none_when_not_categorized(self, mock_categorize_sellers):
        """Should return None when seller couldn't be categorized."""
        mock_categorize_sellers.return_value = ({}, {"沃尔玛"})
        result = categorize_seller("沃尔玛", SAMPLE_CATEGORIES)
        assert result is None
