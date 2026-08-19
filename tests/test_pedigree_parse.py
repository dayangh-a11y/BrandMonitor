"""Unit tests for asbdavani pedigree chart parsing."""

from __future__ import annotations

from src.pedigree.parse import parse_pedigree_html

SAMPLE = """
<html><head>
<meta property="og:title" content="پدیگری اسب بلک بوی | مسابقات اسبدوانی"/>
</head><body>
<table>
<tr>
<td class="bg-blue-100" rowspan="8"><a href="/performance/horses/sire1/pedigree">بتمن</a></td>
<td class="bg-blue-100" rowspan="4"><a href="/performance/horses/ss1/pedigree">لنسکوی</a>
<a href="https://www.pedigreequery.com/lanskoy">پدیگری</a></td>
<td class="bg-blue-100" rowspan="2"><a href="#">-</a></td>
<td class="bg-blue-100" rowspan="1"><a href="#">-</a></td>
</tr>
<tr><td class="bg-red-100" rowspan="1"><a href="#">-</a></td></tr>
<tr>
<td class="bg-red-100" rowspan="2"><a href="#">-</a></td>
<td class="bg-blue-100" rowspan="1"><a href="#">-</a></td>
</tr>
<tr><td class="bg-red-100" rowspan="1"><a href="#">-</a></td></tr>
<tr>
<td class="bg-red-100" rowspan="4"><a href="/performance/horses/sd1/pedigree">دلربا</a></td>
<td class="bg-blue-100" rowspan="2"><a href="/performance/horses/sds1/pedigree">مای جنریشن</a></td>
<td class="bg-blue-100" rowspan="1"><a href="#">-</a></td>
</tr>
<tr><td class="bg-red-100" rowspan="1"><a href="#">-</a></td></tr>
<tr>
<td class="bg-red-100" rowspan="2"><a href="/performance/horses/sdd1/pedigree">پرشین اسپریت</a></td>
<td class="bg-blue-100" rowspan="1"><a href="#">-</a></td>
</tr>
<tr><td class="bg-red-100" rowspan="1"><a href="#">-</a></td></tr>
<tr>
<td class="bg-red-100" rowspan="8"><a href="/performance/horses/dam1/pedigree">ارمغان</a></td>
<td class="bg-blue-100" rowspan="4"><a href="#">-</a></td>
<td class="bg-blue-100" rowspan="2"><a href="#">-</a></td>
<td class="bg-blue-100" rowspan="1"><a href="#">-</a></td>
</tr>
<tr><td class="bg-red-100" rowspan="1"><a href="#">-</a></td></tr>
<tr>
<td class="bg-red-100" rowspan="2"><a href="#">-</a></td>
<td class="bg-blue-100" rowspan="1"><a href="#">-</a></td>
</tr>
<tr><td class="bg-red-100" rowspan="1"><a href="#">-</a></td></tr>
<tr>
<td class="bg-red-100" rowspan="4"><a href="#">-</a></td>
<td class="bg-blue-100" rowspan="2"><a href="#">-</a></td>
<td class="bg-blue-100" rowspan="1"><a href="#">-</a></td>
</tr>
<tr><td class="bg-red-100" rowspan="1"><a href="#">-</a></td></tr>
<tr>
<td class="bg-red-100" rowspan="2"><a href="#">-</a></td>
<td class="bg-blue-100" rowspan="1"><a href="#">-</a></td>
</tr>
<tr><td class="bg-red-100" rowspan="1"><a href="#">-</a></td></tr>
</table>
</body></html>
"""


def test_parse_sire_dam_and_grandparents():
    parsed = parse_pedigree_html(SAMPLE, "subj1")
    assert parsed["subject_name"] == "بلک بوی"
    assert parsed["sire"]["name"] == "بتمن"
    assert parsed["sire"]["source_id"] == "sire1"
    assert parsed["dam"]["name"] == "ارمغان"
    assert parsed["dam"]["source_id"] == "dam1"
    assert parsed["sire_sire"]["name"] == "لنسکوی"
    assert parsed["sire_dam"]["name"] == "دلربا"
    assert parsed["dam_sire"] is None
    assert parsed["dam_dam"] is None
    assert parsed["named_ancestor_count"] == 4


def test_no_invent_on_empty_table():
    parsed = parse_pedigree_html("<html></html>", "x")
    assert parsed["sire"] is None
    assert parsed["dam"] is None
    assert parsed["parse_status"] == "NO_TABLE"
