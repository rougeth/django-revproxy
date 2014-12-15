
import re

from io import BytesIO

from django.template import loader, RequestContext

try:
    from diazo.compiler import compile_theme
except ImportError:  # pragma: no cover
    has_diazo = False
else:
    has_diazo = True
    from lxml import etree


doctype_re = re.compile(br"^<!DOCTYPE\s[^>]+>\s*", re.MULTILINE)

DIAZO_OFF_REQUEST_HEADER = 'HTTP_X_DIAZO_OFF'
DIAZO_OFF_RESPONSE_HEADER = 'X-Diazo-Off'


def asbool(value):
    try:  # pragma: no cover
        is_string = isinstance(value, basestring)
    except NameError:  # Python 3
        is_string = isinstance(value, str)

    if is_string:
        value = value.strip().lower()
        if value in ('true', 'yes', 'on', 'y', 't', '1',):
            return True
        elif value in ('false', 'no', 'off', 'n', 'f', '0'):
            return False
        else:
            raise ValueError("String is not true/false: %r" % value)
    else:
        return bool(value)


class DiazoTransformer(object):

    def __init__(self, request, response):
        self.request = request
        self.response = response

    def should_transform(self):
        """Determine if we should transform the response"""

        if not has_diazo:  # pragma: no cover
            return False

        if asbool(self.request.META.get(DIAZO_OFF_REQUEST_HEADER)):
            return False

        if asbool(self.response.get(DIAZO_OFF_RESPONSE_HEADER)):
            return False

        if self.request.is_ajax():
            return False

        # We actually don't support stream proxy so far
        if self.response.streaming:
            return False

        content_type = self.response.get('Content-Type')
        if not content_type or not (
            content_type.lower().startswith('text/html') or
            content_type.lower().startswith('application/xhtml+xml')
        ):
            return False

        content_encoding = self.response.get('Content-Encoding')
        if content_encoding in ('zip', 'deflate', 'compress',):
            return False

        status_code = str(self.response.status_code)
        if status_code.startswith('3') or \
                status_code == '204' or \
                status_code == '401':
            return False

        if len(self.response.content) == 0:
            return False

        return True

    def transform(self, rules, theme_template, is_html5):

        if not self.should_transform():
            return self.response

        context_instance = RequestContext(self.request)
        theme = loader.render_to_string(theme_template,
                                        context_instance=context_instance)
        output_xslt = compile_theme(
            rules=rules,
            theme=BytesIO(theme.encode('latin1')),
        )

        transform = etree.XSLT(output_xslt)

        content = self.response.unicode_content or self.response.content
        content_doc = etree.fromstring(content, parser=etree.HTMLParser())

        self.response.content = transform(content_doc)

        if is_html5:
            self.set_html5_doctype()

        self.reset_headers()
        return self.response

    def reset_headers(self):
        del self.response['Content-Length']

    def set_html5_doctype(self):
        doctype = b'<!DOCTYPE html>\n'
        content, subs = doctype_re.subn(doctype, self.response.content, 1)

        if not subs:
            self.response.content = doctype + self.response.content

        self.response.content = content
