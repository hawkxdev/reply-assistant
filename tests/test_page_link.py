"""Token link page tests."""

from tests.acceptance.page_runtime import run_page


def test_fragment_plus_sign_stays_a_plus_in_the_header() -> None:
    result = run_page('#token=alpha+beta', 'alpha+beta')

    assert len(result['requests']) == 1
    assert result['requests'][0]['headers'].get('x-api-token') == 'alpha+beta'


def test_interior_space_credential_is_sent_as_decoded() -> None:
    result = run_page('#token=alpha%20beta', 'alpha beta')

    assert len(result['requests']) == 1
    assert result['requests'][0]['headers'].get('x-api-token') == 'alpha beta'
    assert result['reply'] == 'Scripted customer reply.'


def test_interior_tab_credential_is_sent_as_decoded() -> None:
    result = run_page('#token=alpha%09beta', 'alpha\tbeta')

    assert len(result['requests']) == 1
    assert result['requests'][0]['headers'].get('x-api-token') == 'alpha\tbeta'
    assert result['reply'] == 'Scripted customer reply.'


def test_broken_link_reports_the_access_error_at_load() -> None:
    result = run_page('#token=%ZZ', 'expected-test-token', messages=())

    assert result['requests'] == []
    assert 'Access denied' in result['state']
