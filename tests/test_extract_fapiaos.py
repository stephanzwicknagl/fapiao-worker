"""Tests for fapiao/extract.py — inline text strings, no real PDFs needed."""


from fapiao.extract import _approx_eq, _clean, _extract_seller, parse_fapiao

# ── helpers ──────────────────────────────────────────────────────────────────

def test_clean_strips_commas_and_whitespace():
    assert _clean('1,234.56') == '1234.56'
    assert _clean('  99 ') == '99'
    assert _clean('1,000,000.00') == '1000000.00'


def test_approx_eq():
    assert _approx_eq(10.0, 10.01)
    assert _approx_eq(10.0, 9.99)
    assert not _approx_eq(10.0, 10.03)
    assert _approx_eq(5.0, 5.0, tol=0.0)
    assert not _approx_eq(5.0, 5.01, tol=0.0)


# ── garbled / skip detection ──────────────────────────────────────────────────

def test_skip_garbled_no_nian():
    """Pages without 年 are garbled (airline/train ticket PDFs)."""
    result = parse_fapiao('Invoice 12345 amount 100')
    assert result['skip'] is True
    assert result['skip_reason'] == 'garbled text'


def test_skip_continuation_page():
    text = '发票号码：012345678901234\n2024年3月15日\n共 3 页 第 2 页\n名称：测试公司有限公司'
    result = parse_fapiao(text)
    assert result['skip'] is True
    assert '2' in result['skip_reason']


def test_last_page_not_skipped():
    """共 N 页 第 N 页 means last page — should NOT be skipped."""
    text = '发票号码：012345678901234\n2024年3月15日\n共 2 页 第 2 页\n名称：测试公司有限公司'
    result = parse_fapiao(text)
    assert result['skip'] is False


# ── fapiao number ─────────────────────────────────────────────────────────────

def test_fapiao_number_labeled():
    text = '年\n发票号码：012345678901234\n2024年3月5日'
    result = parse_fapiao(text)
    assert result['fapiao_number'] == '012345678901234'


def test_fapiao_number_20digit_fallback():
    text = '年\n2024年1月1日\n00000000000000000001\n金额'
    result = parse_fapiao(text)
    assert result['fapiao_number'] == '00000000000000000001'


def test_fapiao_number_none_when_absent():
    text = '年\n2024年1月1日\n金额'
    result = parse_fapiao(text)
    assert result['fapiao_number'] is None


# ── date parsing ──────────────────────────────────────────────────────────────

def test_date_parsed_correctly():
    text = '年\n2024年3月5日'
    result = parse_fapiao(text)
    assert result['date'] == '2024-03-05'


def test_date_two_digit_day_month():
    text = '年\n2023年12月31日'
    result = parse_fapiao(text)
    assert result['date'] == '2023-12-31'


def test_date_none_when_absent():
    text = '年\n金额100元'
    result = parse_fapiao(text)
    assert result['date'] is None


# ── amount strategies ─────────────────────────────────────────────────────────

def test_s1_walmart_style():
    """S1: （小写）¥xxx"""
    text = '年\n2024年1月1日\n（小写）¥188.50\n名称：沃尔玛（湖北）商业零售有限公司'
    result = parse_fapiao(text)
    assert result['amount'] == '188.50'


def test_s1_fullwidth_yen():
    text = '年\n2024年1月1日\n（小写）￥99.00'
    result = parse_fapiao(text)
    assert result['amount'] == '99.00'


def test_s1_comma_in_amount():
    text = '年\n2024年1月1日\n（小写）¥1,234.56'
    result = parse_fapiao(text)
    assert result['amount'] == '1234.56'


def test_s2_didi_style():
    """S2: （小写）\nxxx\n¥"""
    text = '年\n2024年1月1日\n（小写）\n45.60\n¥'
    result = parse_fapiao(text)
    assert result['amount'] == '45.60'


def test_s3_meituan_prefix():
    """S3: ¥xxx\n大写 — amount precedes 大写"""
    text = '年\n2024年1月1日\n¥55.00\n壹拾贰圆整'
    result = parse_fapiao(text)
    assert result['amount'] == '55.00'


def test_s4_ecommerce_amount_follows_daxie():
    """S4: 大写\n¥xxx"""
    text = '年\n2024年1月1日\n壹佰贰拾叁圆整\n¥123.00'
    result = parse_fapiao(text)
    assert result['amount'] == '123.00'


def test_s4b_restaurant_t_p_v_triplet():
    """S4b: 大写\nT\nP\nV where T = P + V"""
    # T is first after 大写, P is pre-tax, V is VAT. T = P + V.
    text = (
        '年\n2024年1月1日\n'
        '壹佰圆整\n'
        '100.00\n'
        '94.34\n'
        '5.66\n'
    )
    result = parse_fapiao(text)
    assert result['amount'] == '100.00'


def test_s5_metro_format():
    """S5: P\nV\nT\n美国 where T = P + V"""
    text = (
        '年\n2024年1月1日\n'
        '94.34\n'
        '5.66\n'
        '100.00\n'
        '美国驻武汉总领事馆\n'
    )
    result = parse_fapiao(text)
    assert result['amount'] == '100.00'


def test_s6_dominos_bare_yen_triplet():
    """S6: T\n¥  P\n¥  V\n¥ scattered in text"""
    text = (
        '年\n2024年1月1日\n'
        '100.00\n¥\n'
        '94.34\n¥\n'
        '5.66\n¥\n'
    )
    result = parse_fapiao(text)
    assert result['amount'] == '100.00'


def test_amount_none_when_not_found():
    text = '年\n2024年1月1日\n名称：测试公司有限公司'
    result = parse_fapiao(text)
    assert result['amount'] is None


# ── VAT strategies ────────────────────────────────────────────────────────────

def test_v1_walmart_he_ji():
    """V1: 合   计 ¥P ¥V"""
    text = '年\n2024年1月1日\n（小写）¥188.50\n合     计  ¥176.17  ¥12.33'
    result = parse_fapiao(text)
    assert result['vat_amount'] == '12.33'


def test_v2_didi_he_ji():
    """V2: 合\n计\nP\n¥\nV\n¥"""
    text = '年\n2024年1月1日\n（小写）\n45.60\n¥\n合\n计\n42.62\n¥\n2.98\n¥'
    result = parse_fapiao(text)
    assert result['vat_amount'] == '2.98'


def test_v4_restaurant_vat():
    """V4: 大写\nT\nP\nV (third = VAT)"""
    text = (
        '年\n2024年1月1日\n'
        '壹佰圆整\n'
        '100.00\n'
        '94.34\n'
        '5.66\n'
    )
    result = parse_fapiao(text)
    assert result['vat_amount'] == '5.66'


def test_v5_metro_vat():
    """V5: P\nV\nT\n美国 (second = VAT)"""
    text = (
        '年\n2024年1月1日\n'
        '94.34\n'
        '5.66\n'
        '100.00\n'
        '美国驻武汉总领事馆\n'
    )
    result = parse_fapiao(text)
    assert result['vat_amount'] == '5.66'


def test_vat_none_when_not_found():
    text = '年\n2024年1月1日\n（小写）¥50.00'
    result = parse_fapiao(text)
    assert result['vat_amount'] is None


# ── seller extraction ─────────────────────────────────────────────────────────

class TestExtractSeller:
    def test_explicit_name_label(self):
        assert _extract_seller('名称：武汉某餐饮有限公司\n其他内容') == '武汉某餐饮有限公司'

    def test_explicit_name_colon_ascii(self):
        assert _extract_seller('名称:武汉某股份公司') == '武汉某股份公司'

    def test_skips_buyer_name(self):
        """名称 line containing a buyer name should be skipped."""
        text = '名称：美国驻武汉总领事馆\n名称：武汉卖家有限公司'
        assert _extract_seller(text) == '武汉卖家有限公司'

    def test_bare_line_with_company_keyword(self):
        text = '年\n武汉沃歌斯餐饮有限公司\n其他内容'
        assert _extract_seller(text) == '武汉沃歌斯餐饮有限公司'

    def test_returns_none_when_no_seller(self):
        assert _extract_seller('年\n金额 100') is None

    def test_does_not_return_meta_name_line(self):
        """A 名称 field that itself contains '名称' should be ignored."""
        text = '名称：名称标签\n名称：武汉真实卖家有限公司'
        assert _extract_seller(text) == '武汉真实卖家有限公司'


# ── full parse integration ────────────────────────────────────────────────────

def test_full_parse_walmart_style():
    text = (
        '发票号码：012345678901234\n'
        '2024年3月15日\n'
        '（小写）¥188.50\n'
        '合     计  ¥176.17  ¥12.33\n'
        '名称：沃尔玛（湖北）商业零售有限公司\n'
        '年\n'
    )
    result = parse_fapiao(text)
    assert result['skip'] is False
    assert result['fapiao_number'] == '012345678901234'
    assert result['date'] == '2024-03-15'
    assert result['amount'] == '188.50'
    assert result['vat_amount'] == '12.33'
    assert result['seller'] == '沃尔玛（湖北）商业零售有限公司'


def test_full_parse_metro_style():
    text = (
        '发票号码：012345678901235\n'
        '2024年6月1日\n'
        '94.34\n'
        '5.66\n'
        '100.00\n'
        '美国驻武汉总领事馆\n'
        '上海麦德龙商贸有限公司武汉分公司\n'
        '年\n'
    )
    result = parse_fapiao(text)
    assert result['skip'] is False
    assert result['amount'] == '100.00'
    assert result['vat_amount'] == '5.66'
    assert '麦德龙' in result['seller']
