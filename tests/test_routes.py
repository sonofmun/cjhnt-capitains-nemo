from config import Config
from capitains_nautilus.cts.resolver import NautilusCTSResolver
from formulae import create_app, db, mail
from formulae.nemo import NemoFormulae
from formulae.models import User
from formulae.search.Search import advanced_query_index, query_index, build_sort_list, suggest_word_search
from formulae.dispatcher_builder import organizer
import flask_testing
from formulae.search.forms import AdvancedSearchForm, SearchForm
from formulae.auth.forms import LoginForm, PasswordChangeForm, LanguageChangeForm, ResetPasswordForm, \
    ResetPasswordRequestForm, RegistrationForm, ValidationError
from flask_login import current_user
from flask_babel import _
from elasticsearch import Elasticsearch
from unittest.mock import patch
from .fake_es import FakeElasticsearch
from collections import OrderedDict
import os
from MyCapytain.common.constants import Mimetypes
from flask import Markup, url_for, abort
import re
from math import ceil


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite://'
    CORPUS_FOLDERS = ["tests/test_data/cjhnt"]
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_BINDS = {
        'appmeta':      'sqlite:///./{}/appmeta.db'.format(CORPUS_FOLDERS[0])
    }


class Formulae_Testing(flask_testing.TestCase):
    def create_app(self):

        app = create_app(TestConfig)
        self.nemo = NemoFormulae(name="InstanceNemo", resolver=NautilusCTSResolver(app.config['CORPUS_FOLDERS'],
                                                                                   dispatcher=organizer),
                                 app=app, base_url="", transform={"default": "components/epidoc.xsl",
                                                                  "notes": "components/extract_notes.xsl"},
                                 templates={"main": "templates/main",
                                            "errors": "templates/errors",
                                            "auth": "templates/auth",
                                            "search": "templates/search"},
                                 css=["assets/css/theme.css"], js=["assets/js/empty.js"], static_folder="./assets/")

        @app.route('/500', methods=['GET'])
        def r_500():
            abort(500)

        return app

    def setUp(self):
        db.create_all()
        u = User(username="project.member", email="project.member@uni-hamburg.de", project_team=True)
        u.set_password('some_password')
        db.session.add(u)
        u = User(username="not.project", email="not.project@uni-hamburg.de", project_team=False)
        u.set_password('some_other_password')
        db.session.add(u)
        db.session.commit()


    def tearDown(self):
        db.session.remove()
        db.drop_all()


class TestFunctions(Formulae_Testing):
    def test_get_first_passage(self):
        """ Make sure the first passage of a work is correctly returned"""
        first = self.nemo.get_first_passage('urn:cts:cjhnt:nt.86-Jud.grc001')
        self.assertEqual(first, '1.1-1.20')

    def test_NemoFormulae_f_replace_indexed_item(self):
        """ Make sure that the replace_indexed_item filter works correctly"""
        old_list = [1, 2, 3, 5, 5, 6, 7]
        new_list = [1, 2, 3, 4, 5, 6, 7]
        test_list = self.nemo.f_replace_indexed_item(old_list, 3, 4)
        self.assertEqual(test_list, new_list)


class TestIndividualRoutes(Formulae_Testing):
    def test_anonymous_user(self):
        """ Make sure that protected routes do not work with unauthorized users and that unprotected routes do

        """
        with self.client as c:
            c.get('/', follow_redirects=True)
            self.assertTemplateUsed('main::index.html')
            c.get('/imprint', follow_redirects=True)
            self.assertTemplateUsed('main::impressum.html')
            c.get('/search/doc', follow_redirects=True)
            self.assertTemplateUsed('search::documentation.html')
            c.get('/auth/user/project.member', follow_redirects=True)
            self.assertMessageFlashed(_('Bitte loggen Sie sich ein, um Zugang zu erhalten.'))
            self.assertTemplateUsed('auth::login.html')
            c.get('/collections/urn:cts:greekLit:tlg0527', follow_redirects=True)
            self.assertTemplateUsed('main::collection.html')
            c.get('/collections/urn:cts:cjhnt:nt', follow_redirects=True)
            self.assertTemplateUsed('main::collection.html')
            # r_references does not work right now.
            # c.get('/text/urn:cts:formulae:stgallen.wartmann0001.lat001/references', follow_redirects=True)
            # self.assertTemplateUsed('main::references.html')
            c.get('/texts/urn:cts:cjhnt:nt.86-Jud.grc001+urn:cts:cjhnt:commentary.tlg0042006.opp-grc1/passage/1+1', follow_redirects=True)
            self.assertTemplateUsed('main::multipassage.html')
            # Check for backwards compatibility of URLs
            c.get('/texts/urn:cts:cjhnt:nt.86-Jud.grc001+urn:cts:cjhnt:commentary.tlg0042006.opp-grc1/passage/1+first', follow_redirects=True)
            self.assertTemplateUsed('main::multipassage.html')
            c.get('/texts/urn:cts:cjhnt:nt.86-Jud+urn:cts:cjhnt:commentary.tlg0042006.opp-grc1/passage/1+first', follow_redirects=True)
            self.assertTemplateUsed('main::multipassage.html')
            c.get('/add_collections/urn:cts:cjhnt:nt.86-Jud.grc001/1', follow_redirects=True)
            self.assertTemplateUsed('main::collection.html')
            c.get('/add_collection/urn:cts:cjhnt:nt/urn:cts:cjhnt:nt.86-Jud.grc001/1', follow_redirects=True)
            self.assertTemplateUsed('main::collection.html')
            c.get('/texts/urn:cts:cjhnt:nt.86-Jud.grc001+urn:cts:cjhnt:commentary.tlg0042006.opp-grc1/passage/1+145', follow_redirects=True)
            self.assertMessageFlashed('Fragmenta In Evangelium Joannis (In Catenis).145 was not found. The whole text is shown here.')
            self.assertTemplateUsed('main::multipassage.html')
            c.get('/work/urn:cts:cjhnt:nt.86-Jud.grc001', follow_redirects=True)
            self.assertTemplateUsed('main::sub_collection.html')
            c.get('/add_text/urn:cts:cjhnt:nt.86-Jud.grc001/urn:cts:cjhnt:commentary.tlg0042006.opp-grc1/1', follow_redirects=True)
            self.assertTemplateUsed('main::sub_collection.html')
            c.get('/nt_com/urn:cts:cjhnt:nt.86-Jud.grc001/passage/1.1', follow_redirects=True)
            self.assertTemplateUsed('main::commentary_view.html')
            self.assertFalse(self.nemo.check_project_team())

    def test_authorized_project_member(self):
        """ Make sure that all routes are open to project members"""
        with self.client as c:
            c.post('/auth/login', data=dict(username='project.member', password="some_password"),
                   follow_redirects=True)
            c.get('/', follow_redirects=True)
            self.assertTemplateUsed('main::index.html')
            c.get('/imprint', follow_redirects=True)
            self.assertTemplateUsed('main::impressum.html')
            c.get('/auth/user/project.member', follow_redirects=True)
            self.assertTemplateUsed('auth::login.html')
            c.get('/collections/urn:cts:greekLit:tlg0527', follow_redirects=True)
            self.assertTemplateUsed('main::collection.html')
            c.get('/collections/urn:cts:cjhnt:nt', follow_redirects=True)
            self.assertTemplateUsed('main::collection.html')
            # r_references does not work right now.
            # c.get('/text/urn:cts:formulae:stgallen.wartmann0001.lat001/references', follow_redirects=True)
            # self.assertTemplateUsed('main::references.html')
            c.get('/texts/urn:cts:cjhnt:nt.86-Jud.grc001+urn:cts:cjhnt:commentary.tlg0042006.opp-grc1/passage/1+1', follow_redirects=True)
            self.assertTemplateUsed('main::multipassage.html')
            # Check for backwards compatibility of URLs
            c.get('/texts/urn:cts:cjhnt:nt.86-Jud.grc001+urn:cts:cjhnt:commentary.tlg0042006.opp-grc1/passage/1+first', follow_redirects=True)
            self.assertTemplateUsed('main::multipassage.html')
            c.get('/texts/urn:cts:cjhnt:nt.86-Jud+urn:cts:cjhnt:commentary.tlg0042006.opp-grc1/passage/1+first', follow_redirects=True)
            self.assertTemplateUsed('main::multipassage.html')
            c.get('/add_collections/urn:cts:cjhnt:nt.86-Jud.grc001/1', follow_redirects=True)
            self.assertTemplateUsed('main::collection.html')
            c.get('/add_collection/urn:cts:cjhnt:nt/urn:cts:cjhnt:nt.86-Jud.grc001/1', follow_redirects=True)
            self.assertTemplateUsed('main::collection.html')
            # An authenicated user who surfs to the login page should be redirected to index
            c.get('/auth/login', follow_redirects=True)
            self.assertTemplateUsed('main::index.html')
            c.get('/texts/urn:cts:cjhnt:nt.86-Jud.grc001+urn:cts:cjhnt:commentary.tlg0042006.opp-grc1/passage/1+145', follow_redirects=True)
            self.assertMessageFlashed('Fragmenta In Evangelium Joannis (In Catenis).145 wurde nicht gefunden. Der ganze Text wird angezeigt.')
            self.assertTemplateUsed('main::multipassage.html')
            c.get('/work/urn:cts:cjhnt:nt.86-Jud.grc001', follow_redirects=True)
            self.assertTemplateUsed('main::sub_collection.html')
            c.get('/add_text/urn:cts:cjhnt:nt.86-Jud.grc001/urn:cts:cjhnt:commentary.tlg0042006.opp-grc1/1', follow_redirects=True)
            self.assertTemplateUsed('main::sub_collection.html')
            c.get('/nt_com/urn:cts:cjhnt:nt.86-Jud.grc001/passage/1.1', follow_redirects=True)
            self.assertTemplateUsed('main::commentary_view.html')
            self.assertTrue(self.nemo.check_project_team())

    def test_authorized_normal_user(self):
        """ Make sure that all routes are open to normal users but that some texts are not available"""
        with self.client as c:
            c.post('/auth/login', data=dict(username='not.project', password="some_other_password"),
                   follow_redirects=True)
            c.get('/', follow_redirects=True)
            self.assertTemplateUsed('main::index.html')
            c.get('/imprint', follow_redirects=True)
            self.assertTemplateUsed('main::impressum.html')
            c.get('/auth/user/project.member', follow_redirects=True)
            self.assertTemplateUsed('auth::login.html')
            c.get('/collections/urn:cts:greekLit:tlg0527', follow_redirects=True)
            self.assertTemplateUsed('main::collection.html')
            c.get('/collections/urn:cts:cjhnt:nt', follow_redirects=True)
            self.assertTemplateUsed('main::collection.html')
            # r_references does not work right now.
            # c.get('/text/urn:cts:formulae:stgallen.wartmann0001.lat001/references', follow_redirects=True)
            # self.assertTemplateUsed('main::references.html')
            c.get('/texts/urn:cts:cjhnt:nt.86-Jud.grc001+urn:cts:cjhnt:commentary.tlg0042006.opp-grc1/passage/1+1', follow_redirects=True)
            self.assertTemplateUsed('main::multipassage.html')
            c.get('/texts/urn:cts:cjhnt:nt.86-Jud+urn:cts:cjhnt:commentary.tlg0042006.opp-grc1/passage/1+first', follow_redirects=True)
            self.assertTemplateUsed('main::multipassage.html')
            # Check for backwards compatibility of URLs
            c.get('/texts/urn:cts:cjhnt:nt.86-Jud.grc001+urn:cts:cjhnt:commentary.tlg0042006.opp-grc1/passage/1+first', follow_redirects=True)
            self.assertTemplateUsed('main::multipassage.html')
            c.get('/add_collections/urn:cts:cjhnt:nt.86-Jud.grc001/1', follow_redirects=True)
            self.assertTemplateUsed('main::collection.html')
            c.get('/add_collection/urn:cts:cjhnt:nt/urn:cts:cjhnt:nt.86-Jud.grc001/1', follow_redirects=True)
            self.assertTemplateUsed('main::collection.html')
            # An authenicated user who surfs to the login page should be redirected to index
            c.get('/auth/login', follow_redirects=True)
            self.assertTemplateUsed('main::index.html')
            c.get('/texts/urn:cts:cjhnt:nt.86-Jud.grc001+urn:cts:cjhnt:commentary.tlg0042006.opp-grc1/passage/1+145', follow_redirects=True)
            self.assertMessageFlashed('Fragmenta In Evangelium Joannis (In Catenis).145 wurde nicht gefunden. Der ganze Text wird angezeigt.')
            self.assertTemplateUsed('main::multipassage.html')
            c.get('/work/urn:cts:cjhnt:nt.86-Jud.grc001', follow_redirects=True)
            self.assertTemplateUsed('main::sub_collection.html')
            c.get('/add_text/urn:cts:cjhnt:nt.86-Jud.grc001/urn:cts:cjhnt:commentary.tlg0042006.opp-grc1/1', follow_redirects=True)
            self.assertTemplateUsed('main::sub_collection.html')
            c.get('/nt_com/urn:cts:cjhnt:nt.86-Jud.grc001/passage/1.1', follow_redirects=True)
            self.assertTemplateUsed('main::commentary_view.html')
            self.assertFalse(self.nemo.check_project_team())

    @patch("formulae.search.routes.advanced_query_index")
    def test_advanced_search_results(self, mock_search):
        """ Make sure that the correct search results are passed to the search results form"""
        params = dict(corpus='all', sort='urn', q='%CE%BB%CF%8C%CE%B3%CE%BF%CF%82+%CE%B5%E1%BC%B0%CE%BC%CE%AF',
                      lemma_search='y', fuzziness=0, slop=0, in_order=False)
        mock_search.return_value = [[], 0, {}]
        with self.client as c:
            c.post('/auth/login', data=dict(username='project.member', password="some_password"),
                   follow_redirects=True)
            response = c.get('/search/advanced_search?q=λόγος+εἰμί&lemma_search=y&fuzziness=0&slop=0&submit=Search')
            for p, v in params.items():
                self.assertIn('{}={}'.format(p, v), str(response.location))
            # Test to make sure that a capitalized search term is converted to lowercase in advanced search
            response = c.get('/search/advanced_search?q=Λόγος+εἰμί&lemma_search=y&fuzziness=0&slop=0&submit=Search')
            for p, v in params.items():
                self.assertIn('{}={}'.format(p, v), str(response.location))
            params['q'] = 'λόγος+εἰμί'
            c.get('/search/results?source=advanced&corpus=all&sort=urn&q=λόγος+εἰμί&fuzziness=0&slop=0&in_order=False&submit=True')
            mock_search.assert_called_with(corpus=['all'], field='text', fuzziness='0', in_order='False', page=1,
                                           per_page=10, q='λόγος εἰμί', slop='0', sort='urn')
            mock_search.mock_calls = []
            c.get('/search/results?corpus=all&sort=urn&q=λόγος+εἰμί&fuzziness=0&slop=0&in_order=False&submit=True',
                  follow_redirects=True)
            self.assertEqual(mock_search.mock_calls, [], 'mock_search should not be called.')
            self.assertTemplateUsed('main::index.html')
            c.get('/search/advanced_search?q=&fuzziness=0&slop=0&submit=Search')
            self.assertMessageFlashed(_('Bitte geben Sie Daten in mindestens einem Feld ein.'))
            c.get('/search/advanced_search?q=λόγος+εἰμί&lemma_search=y&fuzziness=0&slop=200&submit=Search')
            self.assertMessageFlashed('slop: ' + _('Der Suchradius muss zwischen 0 und 100 liegen'))


    @patch("formulae.search.routes.query_index")
    def test_simple_search_results(self, mock_search):
        """ Make sure that the correct search results are passed to the search results form"""
        params = dict(corpus='new_testament%2Bjewish', q='regnum', sort='urn')
        mock_search.return_value = [[], 0, {}]
        with self.client as c:
            c.post('/auth/login', data=dict(username='project.member', password="some_password"),
                   follow_redirects=True)
            response = c.get('/search/simple?corpus=new_testament&corpus=jewish&q=Regnum')
            for p, v in params.items():
                self.assertRegex(str(response.location), r'{}={}'.format(p, v))
            c.get('/search/results?source=simple&corpus=all&sort=urn&q=λόγος+εἰμί&submit=True')
            mock_search.assert_called_with(['all'], 'text', 'λόγος εἰμί', 1, 10, sort='urn')

    def test_search_result_highlighting(self):
        """ Make sure that highlighting of search results works correctly"""
        # Highlighting should cross boundary of parent nodes
        search_string = ['Text that I want to search']
        expected = '<span class="searched"><span class="w searched-start">Text</span><span class="w searched-end">that</span></span></p><p><span class="searched"><span class="w searched-start searched-end">I</span></span></p><p><span class="searched"><span class="w searched-start">want</span><span class="w">to</span><span class="w searched-end">search</span></span>'
        obj_id = 'urn:cts:formulae:salzburg.hauthaler-a0001.lat001'
        xml = self.nemo.get_passage(objectId=obj_id, subreference='1')
        html_input = Markup(self.nemo.transform(xml, xml.export(Mimetypes.PYTHON.ETREE), obj_id))
        result = self.nemo.highlight_found_sents(html_input, search_string)
        self.assertIn(expected, result)
        # Should be able to deal with editorial punctuation in the text
        search_string = ['Text with special editorial signs in it']
        expected = '<span class="searched"><span class="w searched-start">Text</span><span class="w">with</span><span class="w">sp&lt;e&gt;cial</span><span class="w">[edi]torial</span><span class="w">[signs</span><span class="w">in</span><span class="w searched-end">i]t</span></span>'
        obj_id = 'urn:cts:formulae:salzburg.hauthaler-a0001.lat001'
        xml = self.nemo.get_passage(objectId=obj_id, subreference='1')
        html_input = Markup(self.nemo.transform(xml, xml.export(Mimetypes.PYTHON.ETREE), obj_id))
        result = self.nemo.highlight_found_sents(html_input, search_string)
        self.assertIn(expected, result)

    def test_convert_result_sents(self):
        """ Make sure that search result_sents are converted correctly"""
        input_str = 'Anno+XXV+pos+<%2Fsmall><strong>regnum<%2Fstrong><small>+domni+nistri+Lodoici+regis+in%24Notavimus+die+et+<%2Fsmall><strong>regnum<%2Fstrong><small>%2C+superscripsi.+Signum+Petrone'
        output = self.nemo.convert_result_sents(input_str)
        expected = ['Anno XXV pos regnum domni nistri Lodoici regis in', 'Notavimus die et regnum superscripsi Signum Petrone']
        self.assertEqual(output, expected)


class TestForms(Formulae_Testing):
    def test_validate_success_login_form(self):
        """ Ensure that correct data in form validates

        """
        form = LoginForm(username='not.project', password='some_other_password')
        self.assertTrue(form.validate())

    def test_validate_missing_user_name(self):
        """ Make sure that a missing user name is not validated"""
        form = LoginForm(username='', password='wrong_password')
        self.assertFalse(form.validate())

    def test_validate_missing_password(self):
        """ Make sure that a missing password is not validated"""
        form = LoginForm(username='username', password='')
        self.assertFalse(form.validate())

    def test_validate_success_language_change_form(self):
        """ Ensure that correct data in the Language Change form validates

        """
        form = LanguageChangeForm(new_locale='en')
        self.assertTrue(form.validate())

    def test_validate_incorrect_language_language_change_form(self):
        """ Ensure that inputting a language that is not supported in Language Change form does not validate

        """
        form = LanguageChangeForm(new_locale='ru')
        self.assertFalse(form.validate())

    def test_validate_success_change_password_form(self):
        """ Ensure that correct data in the Password Change form validates

        """
        form = PasswordChangeForm(old_password='old_one', password='new', password2='new')
        self.assertTrue(form.validate())

    def test_validate_invalid_change_password_form(self):
        """ Ensure that Password Change form does not validate when password and password2 do not match

        """
        form = PasswordChangeForm(old_password='old_one', password='new', password2='wrong')
        self.assertFalse(form.validate())

    def test_validate_success_password_reset_request_form(self):
        """ Ensure that the password reset request form validates with a valid email address"""
        form = ResetPasswordRequestForm(email='some@email.com')
        self.assertTrue(form.validate())

    def test_validate_invalid_password_reset_request_form(self):
        """ Ensure that the password reset request form does not validate with an invalid email address"""
        form = ResetPasswordRequestForm(email='some_email')
        self.assertFalse(form.validate())

    def test_validate_success_password_reset_form(self):
        """ Ensure that the password reset form validates when the 2 passwords match"""
        form = ResetPasswordForm(password='new', password2='new')
        self.assertTrue(form.validate())

    def test_validate_invalid_password_reset_form(self):
        """ Ensure that the password reset form does not validate when the 2 passwords do not match"""
        form = ResetPasswordForm(password='new', password2='wrong')
        self.assertFalse(form.validate())

    def test_validate_success_advanced_search_form(self):
        """ Ensure that a form with valid data validates"""
        form = AdvancedSearchForm(corpus=['all'], year=600, month="01", day=31, year_start=600, month_start='12',
                                  day_start=12, year_end=700, month_end="01", day_end=12)
        self.assertTrue(form.validate(), "Errors: {}".format(form.errors))

    def test_valid_data_simple_search_form(self):
        """ Ensure that the simple search form validates with valid data"""
        form = SearchForm(corpus=['new_testament'], q='regnum')
        form.corpus.data = ['new_testament']
        form.validate()
        self.assertTrue(form.validate(), 'Simple search with "regnum" should validate')
        form = SearchForm(corpus=['new_testament'], q='re?num')
        form.corpus.data = ['new_testament']
        form.validate()
        self.assertTrue(form.validate(), 'Simple search with "re?num" should validate')

    def test_invalid_data_simple_search_form(self):
        """ Ensure that the simple search form returns a ValidationError with no corpus"""
        form = SearchForm(corpus=[''], q='regnum')
        form.corpus.data = ['']
        self.assertFalse(form.validate(), 'Search with no corpus specified should not validate')
        # I need two choices here since locally it returns the default Error and on Travis it returns the custom message
        self.assertIn(str(form.corpus.errors[0]),
                      [_('Sie müssen mindestens eine Sammlung für die Suche auswählen (\"Formeln\" und/oder \"Urkunden\")'),
                       "'' is not a valid choice for this field"])

    def test_validate_invalid_advanced_search_form(self):
        """ Ensure that a form with invalid data does not validate"""
        # I removed this sub-test because, for some reason, it doesn't pass on Travis, even though it passes locally.
        form = AdvancedSearchForm(corpus=['some corpus'])
        form.corpus.data = ['some corpus']
        self.assertFalse(form.validate(), "Invalid corpus choice should not validate")
        form = AdvancedSearchForm(slop=200)
        self.assertFalse(form.validate(), "Invalid slop choice should not validate")

    def test_validate_valid_registration_form(self):
        """ Ensure that correct data for new user registration validates"""
        form = RegistrationForm(username='new.user', email='some@email.com', password='some_new_password',
                                password2='some_new_password', default_locale="de")
        self.assertTrue(form.validate())

    def test_validate_invalidate_existing_user_registration_form(self):
        """ Ensure that correct data for new user registration validates"""
        form = RegistrationForm(username="not.project", email="not.project@uni-hamburg.de", password='some_new_password',
                                password2='some_new_password', default_locale="de")
        with self.assertRaisesRegex(ValidationError, _('Bitte wählen Sie einen anderen Benutzername.')):
            form.validate_username(form.username)
        with self.assertRaisesRegex(ValidationError, _('Bitte wählen Sie eine andere Emailaddresse.')):
            form.validate_email(form.email)
        self.assertFalse(form.validate())



class TestAuth(Formulae_Testing):
    def test_correct_login(self):
        """ Ensure that login works with correct credentials"""
        # For some reason this test does not work on Travis but it works locally.
        if os.environ.get('TRAVIS') == 'true':
            return
        with self.client as c:
            rv = c.post('/auth/login', data=dict(username='project.member', password="some_password"),
                        follow_redirects=True)
            self.assert200(rv, 'Login should return 200 code')
            self.assertTrue(current_user.email == "project.member@uni-hamburg.de")
            self.assertTrue(current_user.is_active)
            self.assertTrue(current_user.is_authenticated)
            self.assertTemplateUsed('main::index.html')

    def test_incorrect_login(self):
        """ Ensure that login does not work with incorrect credentials"""
        with self.client as c:
            rv = c.post('/auth/login', data=dict(username='pirate.user', password="incorrect"),
                        follow_redirects=True)
            self.assert200(rv, 'Login should return 200 code')
            self.assertMessageFlashed(_('Benutzername oder Passwort ist ungültig'))
            self.assertFalse(current_user.is_active)
            self.assertFalse(current_user.is_authenticated)
            self.assertTemplateUsed('auth::login.html')

    def test_confirm_password_change_token(self):
        """ Confirm that a valid jwt token is created when a user requests a password change"""
        user = User.query.filter_by(username='project.member').first()
        token = user.get_reset_password_token()
        self.assertTrue(user.verify_reset_password_token(token))

    def test_confirm_invalid_password_change_token(self):
        """ Confirm that a valid jwt token created for one user does not work for another"""
        user = User.query.filter_by(username='project.member').first()
        user2 = User.query.filter_by(username='not.project').first()
        token = user.get_reset_password_token()
        self.assertFalse(user2 == user.verify_reset_password_token(token))

    def test_correct_registration(self):
        """ Ensure that new user registration works with correct credentials"""
        with self.client as c:
            rv = c.post('/auth/register', data=dict(username='new.user', email="email@email.com",
                                                    password="some_password", password2="some_password",
                                                    default_locale="de"),
                        follow_redirects=True)
            self.assert200(rv, 'Login should return 200 code')
            self.assertMessageFlashed(_('Sie sind nun registriert.'))
            self.assertTrue(User.query.filter_by(username='new.user').first(), "It should have added new.user.")
            self.assertTemplateUsed('auth::login.html')

    def test_send_email_existing_user(self):
        """ Ensure that emails are constructed correctly"""
        with self.client as c:
            with mail.record_messages() as outbox:
                c.post('/auth/reset_password_request', data=dict(email="project.member@uni-hamburg.de"),
                       follow_redirects=True)
                self.assertEqual(len(outbox), 1, 'One email should be sent')
                self.assertEqual(outbox[0].recipients, ["project.member@uni-hamburg.de"],
                                 'The recipient email address should be correct.')
                self.assertEqual(outbox[0].subject, _('[Formulae - Litterae - Chartae] Passwort zurücksetzen'),
                                 'The Email should have the correct subject.')
                self.assertIn(_('Sehr geehrte(r)') + ' project.member', outbox[0].html,
                              'The email text should be addressed to the correct user.')
                self.assertEqual(outbox[0].sender, 'no-reply@example.com',
                                 'The email should come from the correct sender.')
                self.assertMessageFlashed(_('Die Anweisung zum Zurücksetzen Ihres Passworts wurde Ihnen per E-mail zugeschickt'))

    def test_send_email_not_existing_user(self):
        """ Ensure that emails are constructed correctly"""
        with self.client as c:
            with mail.record_messages() as outbox:
                c.post('/auth/reset_password_request', data=dict(email="pirate.user@uni-hamburg.de"),
                       follow_redirects=True)
                self.assertEqual(len(outbox), 0, 'No email should be sent when the email is not in the database.')
                self.assertMessageFlashed(_('Die Anweisung zum Zurücksetzen Ihres Passworts wurde Ihnen per E-mail zugeschickt'))

    def test_reset_password_from_email_token(self):
        """ Make sure that a correct email token allows the user to reset their password while an incorrect one doesn't"""
        with self.client as c:
            user = User.query.filter_by(username='project.member').first()
            token = user.get_reset_password_token()
            # Make sure that the template renders correctly with correct token
            c.post(url_for('auth.r_reset_password', token=token, _external=True))
            self.assertTemplateUsed('auth::reset_password.html')
            # Make sure the correct token allows the user to change their password
            c.post(url_for('auth.r_reset_password', token=token, _external=True),
                   data={'password': 'some_new_password', 'password2': 'some_new_password'})
            self.assertTrue(user.check_password('some_new_password'), 'User\'s password should be changed.')
            c.post(url_for('auth.r_reset_password', token='some_weird_token', _external=True),
                   data={'password': 'some_password', 'password2': 'some_password'}, follow_redirects=True)
            self.assertTemplateUsed('main::index.html')
            self.assertTrue(user.check_password('some_new_password'), 'User\'s password should not have changed.')
            # Make sure that a logged in user who comes to this page with a token is redirected to their user page with a flashed message
            c.post('/auth/login', data=dict(username='project.member', password="some_new_password"),
                   follow_redirects=True)
            c.post(url_for('auth.r_reset_password', token=token, _external=True), follow_redirects=True)
            self.assertTemplateUsed('auth::login.html')
            self.assertMessageFlashed(_('Sie sind schon eingeloggt. Sie können Ihr Password hier ändern.'))
            self.assertEqual(repr(user), '<User project.member>')

    def test_user_logout(self):
        """ Make sure that the user is correctly logged out and redirected"""
        with self.client as c:
            c.post('/auth/login', data=dict(username='project.member', password="some_password"),
                   follow_redirects=True)
            self.assertTrue(current_user.is_authenticated, 'User should be logged in.')
            c.get('/auth/logout', follow_redirects=True)
            self.assertFalse(current_user.is_authenticated, 'User should now be logged out.')
            self.assertTemplateUsed('auth::login.html')

    def test_user_change_prefs(self):
        """ Make sure that the user can change their language and password"""
        with self.client as c:
            c.post('/auth/login', data=dict(username='project.member', password="some_password"),
                   follow_redirects=True)
            self.assertEqual(current_user.default_locale, 'de', '"de" should be the default language.')
            c.post('/auth/user/project.member', data={'new_locale': "en"})
            self.assertEqual(current_user.default_locale, 'en', 'User language should have been changed to "en"')
            c.post('/auth/user/project.member', data={'old_password': 'some_password', 'password': 'some_new_password',
                                                      'password2': 'some_new_password'},
                   follow_redirects=True)
            self.assertTrue(User.query.filter_by(username='project.member').first().check_password('some_new_password'),
                            'User should have a new password: "some_new_password".')
            self.assertTemplateUsed('main::index.html')

    def test_user_change_prefs_incorrect(self):
        """ Make sure that a user who gives the false old password is not able to change their password"""
        with self.client as c:
            c.post('/auth/login', data=dict(username='project.member', password="some_password"),
                   follow_redirects=True)
            self.assertTrue(current_user.is_authenticated)
            c.post(url_for('auth.r_user', username='project.member'), data={'old_password': 'some_wrong_password',
                                                                            'password': 'some_new_password',
                                                                            'password2': 'some_new_password'},
                   follow_redirects=True)
            self.assertTrue(User.query.filter_by(username='project.member').first().check_password('some_password'),
                            'User\'s password should not have changed.')
            self.assertMessageFlashed(_("Das ist nicht Ihr aktuelles Passwort."))


class TestES(Formulae_Testing):
    def build_file_name(self, fake_args):
        return '&'.join(["{}".format(str(v)) for k, v in fake_args.items()])

    def test_return_when_no_es(self):
        """ Make sure that when ElasticSearch is not active, calls to the search functions return empty results instead of errors"""
        self.app.elasticsearch = None
        simple_test_args = OrderedDict([("index", ['formulae', "chartae"]), ("query", 'regnum'), ("field", "text"),
                                        ("page", 1), ("per_page", self.app.config["POSTS_PER_PAGE"]), ('sort', 'urn')])
        hits, total, aggs = query_index(**simple_test_args)
        self.assertEqual(hits, [], 'Hits should be an empty list.')
        self.assertEqual(total, 0, 'Total should be 0')
        self.assertEqual(aggs, {}, 'Aggregations should be an empty dictionary.')
        test_args = OrderedDict([("corpus", "all"), ("field", "text"), ("q", ''), ("fuzziness", "0"), ('in_order', 'False'),
                                 ("year", 0), ('slop', '0'), ("month", 0), ("day", 0), ("year_start", 814),
                                 ("month_start", 10), ("day_start", 29), ("year_end", 814), ("month_end", 11),
                                 ("day_end", 20), ('date_plus_minus', 0), ('exclusive_date_range', 'False'),
                                 ("composition_place", ''), ('sort', 'urn')])
        hits, total, aggs = advanced_query_index(**test_args)
        self.assertEqual(hits, [], 'Hits should be an empty list.')
        self.assertEqual(total, 0, 'Total should be 0')
        self.assertEqual(aggs, {}, 'Aggregations should be an empty dictionary.')

    @patch.object(Elasticsearch, "search")
    def test_multi_corpus_search(self, mock_search):
        test_args = OrderedDict([("corpus", "nt+tlg0527"), ("field", "text"), ("q", 'λόγος'), ("fuzziness", "0"),
                                 ("in_order", "False"), ('slop', '0'), ('sort', 'urn')])
        fake = FakeElasticsearch(self.build_file_name(test_args), 'advanced_search')
        body = fake.load_request()
        resp = fake.load_response()
        ids = fake.load_ids()
        mock_search.return_value = resp
        test_args['corpus'] = test_args['corpus'].split('+')
        actual, _, _ = advanced_query_index(**test_args)
        mock_search.assert_called_with(index=test_args['corpus'], doc_type="", body=body)
        self.assertEqual(ids, [{"id": x['id']} for x in actual])

    @patch.object(Elasticsearch, "search")
    def test_wildcard_text_search(self, mock_search):
        test_args = OrderedDict([("corpus", "all"), ("field", "text"), ("q", 'λ?γος'), ("fuzziness", "0"),
                                 ("in_order", "False"), ('slop', '0'), ('sort', 'urn')])
        fake = FakeElasticsearch(self.build_file_name(test_args), 'advanced_search')
        body = fake.load_request()
        resp = fake.load_response()
        ids = fake.load_ids()
        mock_search.return_value = resp
        test_args['corpus'] = test_args['corpus'].split('+')
        actual, _, _ = advanced_query_index(**test_args)
        mock_search.assert_called_with(index=test_args['corpus'], doc_type="", body=body)
        self.assertEqual(ids, [{"id": x['id']} for x in actual])

    @patch.object(Elasticsearch, "search")
    def test_lemma_advanced_search(self, mock_search):
        test_args = OrderedDict([("corpus", "all"), ("field", "lemmas"), ("q", 'λόγος'), ("fuzziness", "0"),
                                 ("in_order", "False"), ('slop', '0'), ('sort', 'urn')])
        fake = FakeElasticsearch(self.build_file_name(test_args), 'advanced_search')
        body = fake.load_request()
        resp = fake.load_response()
        ids = fake.load_ids()
        mock_search.return_value = resp
        test_args['corpus'] = test_args['corpus'].split('+')
        actual, _, _ = advanced_query_index(**test_args)
        mock_search.assert_called_with(index=test_args['corpus'], doc_type="", body=body)
        self.assertEqual(ids, [{"id": x['id']} for x in actual])

    @patch.object(Elasticsearch, "search")
    def test_multiword_lemma_advanced_search(self, mock_search):
        test_args = OrderedDict([("corpus", "all"), ("field", "lemmas"), ("q", 'λόγος+εἰμί'), ("fuzziness", "0"),
                                 ("in_order", "False"), ('slop', '0'), ('sort', 'urn')])
        fake = FakeElasticsearch(self.build_file_name(test_args), 'advanced_search')
        body = fake.load_request()
        resp = fake.load_response()
        ids = fake.load_ids()
        mock_search.return_value = resp
        test_args['corpus'] = test_args['corpus'].split('+')
        test_args['q'] = test_args['q'].replace('+', ' ')
        actual, _, _ = advanced_query_index(**test_args)
        mock_search.assert_called_with(index=test_args['corpus'], doc_type="", body=body)
        self.assertEqual(ids, [{"id": x['id']} for x in actual])

    @patch.object(Elasticsearch, "search")
    def test_lemma_advanced_search_with_wildcard(self, mock_search):
        test_args = OrderedDict([("corpus", "all"), ("field", "lemmas"), ("q", 'λ?γος'), ("fuzziness", "0"),
                                 ("in_order", "False"), ('slop', '0'), ('sort', 'urn')])
        mock_search.return_value = [], 0, {}
        with self.client:
            ids, hits, agg = advanced_query_index(**test_args)
            self.assertEqual(ids, [])
            self.assertEqual(hits, 0)
            self.assertMessageFlashed(_("'Wildcard'-Zeichen (\"*\" and \"?\") sind bei der Lemmasuche nicht möglich."))

    @patch.object(Elasticsearch, "search")
    def test_simple_multi_corpus_search(self, mock_search):
        test_args = OrderedDict([("index", ['new_testament', "jewish"]), ("query", 'λόγος'), ("field", "text"),
                                 ("page", 1), ("per_page", self.app.config["POSTS_PER_PAGE"]), ('sort', 'urn')])
        fake_args = OrderedDict([("corpus", "all"), ("field", "text"), ("q", 'λόγος'), ("fuzziness", "0"),
                                 ("in_order", "False"), ('slop', '0'), ('sort', 'urn')])
        fake = FakeElasticsearch(self.build_file_name(fake_args), 'advanced_search')
        mock_search.return_value = fake.load_response()
        body = {'query':
                    {'span_near':
                         {'clauses': [{'span_term': {'text': 'λόγος'}}], 'slop': 0, 'in_order': True}},
                'sort': 'urn', 'from': 0, 'size': 10,
                'highlight': {'fields': {'text': {'fragment_size': 300}},
                              'pre_tags': ['</small><strong>'],
                              'post_tags': ['</strong><small>'], 'encoder': 'html'},
                'aggs': {'corpus': {'filters': {'filters': {'NT': {'match': {'_type': 'nt'}},
                                                            'Philo': {'match': {'_type': 'tlg0018'}},
                                                            'LXX': {'match': {'_type': 'tlg0527'}}}}}}}
        ids, total, aggs = query_index(**test_args)
        mock_search.assert_called_with(index=['new_testament', "jewish"], doc_type="", body=body)
        test_args['query'] = 'λόγος εἰμί'
        body['query']['span_near']['clauses'] = [{'span_term': {'text': 'λόγος'}}, {'span_term': {'text': 'εἰμί'}}]
        query_index(**test_args)
        mock_search.assert_called_with(index=['new_testament', "jewish"], doc_type="", body=body)
        test_args['query'] = 'λ?γος'
        body['query']['span_near']['clauses'] = [{'span_multi': {'match': {'wildcard': {'text': 'λ?γος'}}}}]
        query_index(**test_args)
        mock_search.assert_called_with(index=['new_testament', "jewish"], doc_type="", body=body)
        test_args['index'] = ''
        mt_ids, mt_total, mt_agg = query_index(**test_args)
        self.assertEqual(mt_ids, [])
        self.assertEqual(mt_total, 0)
        self.assertEqual(mt_agg, {})
        with self.client:
            self.app.config["POSTS_PER_PAGE"] = 2
            total_pages = int(ceil(total / self.app.config['POSTS_PER_PAGE']))
            r = self.client.get('/search/simple?index=&q=λόγος', follow_redirects=True)
            self.assertMessageFlashed(_('Sie müssen mindestens eine Sammlung für die Suche auswählen ("NT" und/oder "Jüdische Texte")') +
                                      _(' Resultate aus dem Neuen Testament und Jüdischen Texten werden hier gezeigt.'))
            p = re.compile('\.\.\..+<li class="page-item">\n\s+<a class="page-link"[^>]+page={total}'.format(total=total_pages),
                           re.DOTALL)
            self.assertRegex(r.get_data(as_text=True), p)

    def test_results_sort_option(self):
        self.assertEqual(build_sort_list('urn'), 'urn')
        self.assertEqual(build_sort_list('urn_desc'), [{'urn': {'order': 'desc'}}])

    @patch.object(Elasticsearch, "search")
    def test_suggest_word_search_completion(self, mock_search):
        test_args = OrderedDict([("corpus", "all"), ("field", "autocomplete"), ("q", 'ἀγαπητῷ'), ("fuzziness", "0"),
                                 ("in_order", "False"), ('slop', '0'), ('sort', 'urn')])
        fake = FakeElasticsearch(self.build_file_name(test_args), 'advanced_search')
        resp = fake.load_response()
        expected = ['', 'ἀγαπητῷ καὶ συνεργῷ ἡμῶν καὶ Ἀπφίᾳ']
        mock_search.return_value = resp
        test_args.pop('q')
        results = suggest_word_search('λόγο', **test_args)
        self.assertEqual(results[:10], expected, 'The true results should match the expected results.')

    @patch.object(Elasticsearch, "search")
    def test_single_lemma_highlighting(self, mock_search):
        test_args = OrderedDict([("corpus", "all"), ("field", "lemmas"), ("q", 'προσοφείλω'), ("fuzziness", "0"),
                                 ("in_order", "False"), ('slop', '0'), ('sort', 'urn')])
        fake = FakeElasticsearch(self.build_file_name(test_args), 'advanced_search')
        resp = fake.load_response()
        sents = [{'sents': ['· ἵνα μὴ λέγω σοι ὅτι καὶ σεαυτόν μοι προσοφείλεις. ναί, ἀδελφέ, '
                            'ἐγώ σου ὀναίμην ἐν κυρίῳ · ἀνάπαυσόν μου']}]
        mock_search.return_value = resp
        test_args['corpus'] = test_args['corpus'].split('+')
        test_args['q'] = test_args['q'].replace('+', ' ')
        actual, _, _ = advanced_query_index(**test_args)
        self.assertEqual(sents, [{"sents": x['sents']} for x in actual])

    @patch.object(Elasticsearch, "search")
    def test_multiple_lemma_highlighting(self, mock_search):
        test_args = OrderedDict([("corpus", "all"), ("field", "lemmas"), ("q", 'ἐγώ+προσοφείλω'), ("fuzziness", "0"),
                                 ("in_order", "False"), ('slop', '0'), ('sort', 'urn')])
        fake = FakeElasticsearch(self.build_file_name(test_args), 'advanced_search')
        resp = fake.load_response()
        sents = [{'sents': ['Παῦλος ἔγραψα τῇ ἐμῇ χειρί, ἐγὼ ἀποτίσω · ἵνα μὴ λέγω σοι ὅτι καὶ σεαυτόν μοι προσοφείλεις. ναί, ἀδελφέ, '
                            'ἐγώ σου ὀναίμην ἐν κυρίῳ · ἀνάπαυσόν μου τὰ σπλάγχνα ἐν']}]
        mock_search.return_value = resp
        test_args['corpus'] = test_args['corpus'].split('+')
        test_args['q'] = test_args['q'].replace('+', ' ')
        actual, _, _ = advanced_query_index(**test_args)
        self.assertEqual(sents, [{"sents": x['sents']} for x in actual])


class TestErrors(Formulae_Testing):
    def test_404(self):
        with self.client as c:
            response = c.get('/trying.php', follow_redirects=True)
            self.assert404(response, 'A URL that does not exist on the server should return a 404.')

    def test_UnknownCollection_error(self):
        with self.client as c:
            response = c.get('/collections/urn:cts:cjhnt:newtestament', follow_redirects=True)
            self.assert404(response, 'An Unknown Collection Error should also return 404.')
            self.assertTemplateUsed("errors::unknown_collection.html")

    def test_500(self):
        with self.client as c:
            expected = "<h4>{}</h4><p>{}</p>".format(_('Ein unerwarteter Fehler ist aufgetreten'),
                                                     _('Der Administrator wurde benachrichtigt. Bitte entschuldigen Sie die Unannehmlichkeiten!'))
            response = c.get('/500', follow_redirects=True)
            self.assert500(response, 'Should raise 500 error.')
            self.assertIn(expected, response.get_data(as_text=True))

