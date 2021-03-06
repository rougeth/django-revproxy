
import sys

if sys.version_info >= (3, 0, 0):
    from urllib.error import HTTPError
else:
    from urllib2 import HTTPError

from io import BytesIO

from django.test import RequestFactory, TestCase
from mock import patch, MagicMock
from revproxy.response import HOP_BY_HOP_HEADERS
from revproxy.views import ProxyView

from .utils import response_like_factory


class CustomProxyView(ProxyView):
    upstream = "http://www.example.com"
    diazo_rules = None


class ResponseTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def tearDown(self):
        CustomProxyView.upstream = "http://www.example.com"
        CustomProxyView.diazo_rules = None

    def test_broken_response(self):
        request = self.factory.get('/')

        error = HTTPError(CustomProxyView.upstream, 500, 'Internal Error',
                          {}, BytesIO(b'Testing'))
        urllib2_mock = MagicMock(side_effect=error)

        urllib2_patch = patch(
            'revproxy.views.urlopen',
            new=urllib2_mock,
        )

        with urllib2_patch:
            response = CustomProxyView.as_view()(request, '/')

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.content, b'Testing')

    def test_location_replaces_request_host(self):
        headers = {'Location': 'http://www.example.com'}
        path = "/path"
        request = self.factory.get(path)

        get_proxy_response = response_like_factory(request, headers, 200)

        urllib2_urlopen_patcher = patch(
            'revproxy.views.urlopen',
            new=get_proxy_response
        )
        with urllib2_urlopen_patcher:
            response = CustomProxyView.as_view()(request, path)

        location = "http://" + request.get_host()
        self.assertEqual(location, response['Location'])

    def test_location_replaces_secure_request_host(self):
        CustomProxyView.upstream = "https://www.example.com"

        headers = {'Location': 'https://www.example.com'}
        path = "/path"
        request = self.factory.get(
            path,
            # using kwargs instead of the secure parameter because it
            #   works only after Django 1.7
            **{
                'wsgi.url_scheme': 'https'  # tell factory to use
            }                               # https over http
        )

        get_proxy_response = response_like_factory(request, headers, 200)

        urllib2_urlopen_patcher = patch(
            'revproxy.views.urlopen',
            new=get_proxy_response
        )

        with urllib2_urlopen_patcher:
            response = CustomProxyView.as_view()(request, path)

        location = "https://" + request.get_host()
        self.assertEqual(location, response['Location'])

    def test_response_headers_are_not_in_hop_by_hop_headers(self):
        path = "/"
        request = self.factory.get(path)
        get_proxy_response = response_like_factory(request, {}, 200)

        urllib2_urlopen_patcher = patch(
            'revproxy.views.urlopen',
            new=get_proxy_response
        )

        with urllib2_urlopen_patcher:
            response = CustomProxyView.as_view()(request, path)

        response_headers = response._headers

        for header in response_headers:
            self.assertTrue(header not in HOP_BY_HOP_HEADERS)

    def test_response_code_remains_the_same(self):
        path = "/"
        request = self.factory.get(path)
        retcode = 300
        get_proxy_response = response_like_factory(request, {}, retcode)

        urllib2_urlopen_patcher = patch(
            'revproxy.views.urlopen',
            new=get_proxy_response
        )

        with urllib2_urlopen_patcher:
            response = CustomProxyView.as_view()(request, path)

        self.assertEqual(response.status_code, retcode)

    def test_response_content_remains_the_same(self):
        path = "/"
        request = self.factory.get(path)
        retcode = 300
        get_proxy_response = response_like_factory(request, {}, retcode)

        urllib2_urlopen_patcher = patch(
            'revproxy.views.urlopen',
            new=get_proxy_response
        )

        with urllib2_urlopen_patcher:
            response = CustomProxyView.as_view()(request, path)

        response_content = response.content

        # had to prefix it with 'b' because Python 3 treats str and byte
        # differently
        self.assertEqual(b'Fake file', response_content)
