
import sys

if sys.version_info >= (3, 0, 0):
    from urllib.parse import parse_qs
else:
    from urlparse import parse_qs

from django.contrib.auth.models import AnonymousUser, User
from django.test import TestCase, RequestFactory

from mock import patch

from revproxy.views import ProxyView


class RequestTest(TestCase):

    def setUp(self):
        # Every test needs access to the request factory.
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username='jacob', email='jacob@example.com', password='top_secret')

        self.urllib2_Request_patcher = patch('revproxy.views.Request')
        self.urllib2_urlopen_patcher = patch('revproxy.views.urlopen')
        self.response_patcher = patch('revproxy.views.HttpProxyResponse')

        self.urllib2_Request = self.urllib2_Request_patcher.start()
        self.urllib2_urlopen = self.urllib2_urlopen_patcher.start()
        self.responser = self.response_patcher.start()

    def tearDown(self):
        self.urllib2_Request_patcher.stop()
        self.urllib2_urlopen_patcher.stop()
        self.responser = self.response_patcher.stop()

    def test_default_add_remote_user_attr(self):
        proxy_view = ProxyView()
        self.assertFalse(proxy_view.add_remote_user)

    def test_remote_user_authenticated(self):
        class CustomProxyView(ProxyView):
            add_remote_user = True
            upstream = 'http://www.example.com'

        request = self.factory.get('/')
        request.user = self.user

        response = CustomProxyView.as_view()(request, '/test')

        request_url = 'http://www.example.com/test'
        request_headers = {'REMOTE_USER': 'jacob', u'Cookie': u''}
        self.urllib2_Request.assert_called_with(request_url,
                                                headers=request_headers)

    def test_remote_user_anonymous(self):
        class CustomProxyView(ProxyView):
            add_remote_user = True
            upstream = 'http://www.example.com'

        request = self.factory.get('/')
        request.user = AnonymousUser()

        response = CustomProxyView.as_view()(request, '/test/anonymous/')

        request_url = 'http://www.example.com/test/anonymous/'
        request_headers = {u'Cookie': u''}
        self.urllib2_Request.assert_called_with(request_url,
                                                headers=request_headers)

    def test_simple_get(self):
        class CustomProxyView(ProxyView):
            upstream = 'http://www.example.com'

        get_data = {'a': ['b'], 'c': ['d'], 'e': ['f']}
        request = self.factory.get('/', get_data)
        response = CustomProxyView.as_view()(request, '/')

        assert self.urllib2_Request.called

        called_qs = self.urllib2_Request.call_args[0][0].split('?')[-1]
        called_get_data = parse_qs(called_qs)
        self.assertEqual(called_get_data, get_data)

    def test_get_with_attr_list(self):
        class CustomProxyView(ProxyView):
            upstream = 'http://www.example.com'

        get_data = {
            u'a': [u'a', u'b', u'c', u'd'],
            u'foo': [u'bar'],
        }
        request = self.factory.get('/', get_data)
        response = CustomProxyView.as_view()(request, '/')

        assert self.urllib2_Request.called
        called_qs = self.urllib2_Request.call_args[0][0].split('?')[-1]

        called_get_data = parse_qs(called_qs)
        self.assertEqual(called_get_data, get_data)

    def test_post_and_get(self):
        class CustomProxyView(ProxyView):
            upstream = 'http://www.example.com'

        get_data = {'x': ['y', 'z']}
        post_data = {'a': ['b'], 'c': ['d'], 'e': ['f']}

        request = self.factory.post('/?x=y&x=z', post_data)
        response = CustomProxyView.as_view()(request, '/')

        assert self.urllib2_Request.called
        called_qs = self.urllib2_Request.call_args[0][0].split('?')[-1]

        # Check for GET data
        called_get_data = parse_qs(called_qs)
        self.assertEqual(called_get_data, get_data)

        # Check for POST data
        self.urllib2_Request().add_data.assert_called_with(request.body)

    def test_put(self):
        class CustomProxyView(ProxyView):
            upstream = 'http://www.example.com'

        request_data = {'a': ['b'], 'c': ['d'], 'e': ['f']}

        request = self.factory.put('/', request_data)
        response = CustomProxyView.as_view()(request, '/')

        assert self.urllib2_Request.called

        # Check for request data
        self.urllib2_Request().add_data.assert_called_with(request.body)

        self.assertEqual(self.urllib2_Request().get_method(), 'PUT')

    def test_simple_rewrite(self):
        class CustomProxyView(ProxyView):
            upstream = 'http://www.example.com'
            add_remote_user = False
            rewrite = (
                (r'^/yellow/star/?$', r'/black/hole/'),
                (r'^/foo/$', r'/bar'),
            )

        request = self.factory.get('/yellow/star')
        response = CustomProxyView.as_view()(request, '/yellow/star')

        self.assertEqual(response.url, '/black/hole/')
        self.assertEqual(response.status_code, 302)

    def test_rewrite_with_get(self):
        class CustomProxyView(ProxyView):
            upstream = 'http://www.example.com'
            add_remote_user = False
            rewrite = (
                (r'^/yellow/star/$', r'/black/hole/'),
                (r'^/foo/(.*)$', r'/bar\1'),
            )

        data = {'a': ['1'], 'b': ['c']}
        request = self.factory.get('/foo/', data)
        response = CustomProxyView.as_view()(request, '/foo/')

        path, querystring = response.url.split('?')
        self.assertEqual(path, '/bar')
        self.assertEqual(response.status_code, 302)

        response_data = parse_qs(querystring)
        self.assertEqual(response_data, data)

    def test_rewrite_to_external_location(self):
        class CustomProxyView(ProxyView):
            upstream = 'http://www.example.com'
            add_remote_user = False
            rewrite = (
                (r'^/yellow/star/?$', r'http://www.mozilla.org/'),
            )

        request = self.factory.get('/yellow/star/')
        response = CustomProxyView.as_view()(request, '/yellow/star/')

        self.assertEqual(response.url, 'http://www.mozilla.org/')
        self.assertEqual(response.status_code, 302)

    def test_rewrite_to_view_name(self):
        class CustomProxyView(ProxyView):
            upstream = 'http://www.example.com'
            add_remote_user = False
            rewrite = (
                (r'^/yellow/star/$', r'login'),
            )

        request = self.factory.get('/yellow/star/')
        response = CustomProxyView.as_view()(request, '/yellow/star/')

        self.assertEqual(response.url, '/accounts/login/')
        self.assertEqual(response.status_code, 302)
