"""Acceptance for token links."""

import json

import pytest

from tests.acceptance.page_runtime import run_page

# === Credentials ===


@pytest.mark.xfail(strict=True, reason='issue 98: page sends the link token')
def test_link_token_protects_every_suggestion_request() -> None:
    result = run_page(
        '#token=shared-test-token',
        'shared-test-token',
        messages=('First question', 'Second question'),
    )

    assert len(result['requests']) == 2
    assert [
        request['headers'].get('x-api-token') for request in result['requests']
    ] == [
        'shared-test-token',
        'shared-test-token',
    ]
    assert [request['url'] for request in result['requests']] == [
        'https://demo.example.test/api/suggest',
        'https://demo.example.test/api/suggest',
    ]
    assert [json.loads(request['body']) for request in result['requests']] == [
        {'message': 'First question'},
        {'message': 'Second question'},
    ]
    assert result['reply'] == 'Scripted customer reply.'
    reloaded = run_page('#token=shared-test-token', 'shared-test-token')
    assert reloaded['requests'][0]['headers'].get('x-api-token') == 'shared-test-token'


@pytest.mark.xfail(strict=True, reason='issue 98: decode the token exactly once')
def test_encoded_fragment_token_is_decoded_once() -> None:
    result = run_page('#note=ignore&token=alpha%252Bbeta%2Btail', 'alpha%2Bbeta+tail')

    assert len(result['requests']) == 1
    assert result['requests'][0]['headers'].get('x-api-token') == 'alpha%2Bbeta+tail'
    assert result['reply'] == 'Scripted customer reply.'


# === Rejections ===


@pytest.mark.parametrize('language', ['en', 'ru'])
@pytest.mark.xfail(strict=True, reason='issue 98: localized access rejection')
def test_wrong_token_has_a_localized_access_error(language: str) -> None:
    result = run_page(
        '#token=wrong-test-token', 'expected-test-token', language=language
    )

    assert len(result['requests']) == 1
    assert result['reply'] == ''
    if language == 'ru':
        assert (
            '\u0414\u043e\u0441\u0442\u0443\u043f '
            '\u0437\u0430\u043f\u0440\u0435\u0449\u0451\u043d' in result['state']
        )
    else:
        assert 'Access denied' in result['state']
    assert 'wrong-test-token' not in result['state']


@pytest.mark.parametrize(
    'suffix',
    [
        '#token=',
        '#token=first&token=second',
        '#token=%ZZ',
        '#token=%',
        '#token=%E0%A4%A',
        '#token=line%0Abreak',
    ],
    ids=['empty', 'duplicate', 'invalid_escape', 'incomplete_escape', 'utf8', 'header'],
)
@pytest.mark.xfail(strict=True, reason='issue 98: reject invalid link credentials')
def test_invalid_fragment_never_sends_a_suggestion(suffix: str) -> None:
    result = run_page(suffix, 'expected-test-token')

    assert result['requests'] == []
    assert 'Access denied' in result['state']


# === Privacy ===


@pytest.mark.parametrize('surface', ['visible', 'logs', 'storage', 'cookies'])
@pytest.mark.xfail(strict=True, reason='issue 98: keep the token out of other surfaces')
def test_link_token_is_confined_to_request_headers(surface: str) -> None:
    result = run_page('#token=privacy-test-token', 'privacy-test-token')

    assert len(result['requests']) == 1
    assert result['requests'][0]['headers'].get('x-api-token') == 'privacy-test-token'
    assert 'privacy-test-token' not in json.dumps(result[surface])


# === Compatibility ===


@pytest.mark.xfail(strict=True, reason='issue 98: sanitize transport errors')
def test_transport_error_does_not_disclose_the_link_token() -> None:
    result = run_page(
        '#token=transport-test-token',
        'transport-test-token',
        failure_message='transport-test-token failed',
    )

    assert len(result['requests']) == 1
    assert result['reply'] == ''
    assert 'Error' in result['state']
    assert 'transport-test-token' not in result['state']


def test_local_demo_without_a_token_still_answers() -> None:
    result = run_page('', None)

    assert len(result['requests']) == 1
    assert 'x-api-token' not in result['requests'][0]['headers']
    assert result['reply'] == 'Scripted customer reply.'


def test_query_token_does_not_authorize_the_page() -> None:
    result = run_page(
        '?token=query-test-token#note=not-a-credential', 'query-test-token'
    )

    assert len(result['requests']) == 1
    assert 'x-api-token' not in result['requests'][0]['headers']
    assert result['reply'] == ''
