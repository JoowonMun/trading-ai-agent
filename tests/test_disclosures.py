import pytest

from agent.analysis.disclosures import classify


@pytest.mark.parametrize("title, expected", [
    ("유상증자결정", ("rights_issue", True)),
    ("[기재정정]유상증자 결정", ("rights_issue", True)),
    ("주요사항보고서(자기주식취득결정)", ("buyback", False)),
    ("연결재무제표기준영업(잠정)실적(공정공시)", ("earnings", False)),
    ("현금ㆍ현물배당결정", ("dividend", False)),
    ("감사보고서제출(감사의견 의견거절)", ("other", True)),
    ("임원ㆍ주요주주특정증권등소유상황보고서", ("other", False)),
])
def test_classify(title, expected):
    assert classify(title) == expected
