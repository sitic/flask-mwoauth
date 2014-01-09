#!/usr/bin/env python
# MediaWiki OAuth connector for Flask
#
# Requires flask-oauth
#
# (C) 2013 Merlijn van Deen <valhallasw@arctus.nl>
# Licensed under the MIT License // http://opensource.org/licenses/MIT
#

__version__ = '0.1.14'

import urllib
from flask import request, session, redirect, url_for, flash, Blueprint
from flask_oauth import OAuth, OAuthRemoteApp, OAuthException, parse_response

class MWOAuthRemoteApp(OAuthRemoteApp):
     def handle_oauth1_response(self):
        """Handles an oauth1 authorization response.  The return value of
        this method is forwarded as first argument to the handling view
        function.
        """
        client = self.make_client()
        resp, content = client.request('%s&oauth_verifier=%s' % (
            self.expand_url(self.access_token_url),
            request.args['oauth_verifier'],
        ), self.access_token_method)
        print resp, content
        data = parse_response(resp, content)
        if not self.status_okay(resp):
            raise OAuthException('Invalid response from ' + self.name,
                                 type='invalid_response', data=data)
        return data

class MWOAuth(object):
    def __init__(self,
                 base_url='https://www.mediawiki.org/w',
                 clean_url='https://www.mediawiki.org/wiki',
                 default_return_to='index',
                 consumer_key=None, consumer_secret=None):
        if not consumer_key or not consumer_secret:
            raise Exception('MWOAuthBlueprintFactory needs consumer key and secret')
        self.base_url = base_url

        self.default_return_to = default_return_to

        self.oauth = OAuth()
        self.mwoauth = MWOAuthRemoteApp(self.oauth, 'mw.org',
            base_url = base_url + "/index.php",
            request_token_url=base_url + "/index.php",
            request_token_params = {'title': 'Special:OAuth/initiate',
                                    'oauth_callback': 'oob'},
            access_token_url=base_url + "/index.php?title=Special:OAuth/token",
            authorize_url=clean_url + '/Special:OAuth/authorize',
            consumer_key=consumer_key,
            consumer_secret=consumer_secret,
        )
        self.oauth.remote_apps['mw.org'] = self.mwoauth

        @self.mwoauth.tokengetter
        def get_mwo_token(token=None):
            return session.get('mwo_token')

        self.bp = Blueprint('mwoauth', __name__)

        @self.bp.route('/logout')
        def logout():
            session['mwo_token'] = None
            session['username'] = None
            return "Logged out!"

        @self.bp.route('/login')
        def login():
            redirector = self.mwoauth.authorize()

            if 'next' in request.args:
                oauth_token = session[self.mwoauth.name + '_oauthtok'][0]
                session[oauth_token + '_target'] = request.args['next']

            redirector.headers['Location'] += "&oauth_consumer_key=" + self.mwoauth.consumer_key
            return redirector

        @self.bp.route('/oauth-callback')
        @self.mwoauth.authorized_handler
        def oauth_authorized(resp):
            next_url_key = request.args['oauth_token'] + '_target'
            default_url = url_for(self.default_return_to)

            next_url = session.pop(next_url_key, default_url)

            if resp is None:
                flash(u'You denied the request to sign in.')
                return redirect(next_url)
            session['mwo_token'] = (
                resp['oauth_token'],
                resp['oauth_token_secret']
            )

            username = self.get_current_user(False)
            flash('You were signed in, %s!' % username)
            
            return redirect(next_url)

    def request(self, api_query):
        """ e.g. {'action': 'query', 'meta': 'userinfo'}. format=json not required
            function returns a python dict that resembles the api's json response
        """
        api_query['format'] = 'json'
        return self.mwoauth.post(self.base_url + "/api.php?" + urllib.urlencode(api_query),
                                 content_type="text/plain").data

    def get_current_user(self, cached=True):
        if cached:
            return session.get('username')

        try:
            data = self.request({'action': 'query', 'meta': 'userinfo'})
            session['username'] = data['query']['userinfo']['name']
        except KeyError:
            session['username'] = None
            if data['error']['code'] == "mwoauth-invalid-authorization":
                flash(u'Access to this application was revoked. Please re-login!')
            else:
                raise
        except OAuthException:
            session['username'] = None
        return session['username']
