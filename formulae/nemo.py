from flask import flash, url_for, Markup, request, send_from_directory
from flask_login import current_user, login_user, logout_user, login_required
from werkzeug.utils import redirect
from werkzeug.urls import url_parse
from flask_nemo import Nemo
from MyCapytain.common.constants import Mimetypes
from MyCapytain.resources.prototypes.cts.inventory import CtsWorkMetadata, CtsEditionMetadata
from MyCapytain.errors import UnknownCollection
from .app import db
from .forms import LoginForm, PasswordChangeForm
from lxml import etree
from .models import User


class NemoFormulae(Nemo):

    ROUTES = [
        ("/", "r_index", ["GET"]),
        ("/collections", "r_collections", ["GET"]),
        ("/collections/<objectId>", "r_collection", ["GET"]),
        ("/text/<objectId>/references", "r_references", ["GET"]),
        ("/texts/<objectIds>/passage/<subreferences>", "r_multipassage", ["GET"]),
        ("/login", "r_login", ["GET", "POST"]),
        ("/logout", "r_logout", ["GET"]),
        ("/user/<username>", "r_user", ["GET", "POST"]),
        ("/add_text/<objectIds>/<reffs>", "r_add_text_collections", ["GET"]),
        ("/add_text/<objectId>/<objectIds>/<reffs>", "r_add_text_collection", ["GET"])
    ]
    SEMANTIC_ROUTES = [
        "r_collection", "r_references", "r_multipassage"
    ]

    FILTERS = [
        "f_formatting_passage_reference",
        "f_i18n_iso",
        "f_order_resource_by_lang",
        "f_hierarchical_passages",
        "f_is_str",
        "f_i18n_citation_type",
        "f_slugify",
        "f_make_members"
    ]

    CACHED = [
        # Routes
        "r_index", "r_collection", "r_collections", "r_references", "r_assets", "r_multipassage",
        # Controllers
        "get_inventory", "get_collection", "get_reffs", "get_passage", "get_siblings",
        # Translater
        "semantic", "make_coins", "expose_ancestors_or_children", "make_members", "transform",
        # Business logic
        # "view_maker", "route", #"render",
    ]

    PROTECTED = [
        "r_index", "r_collections", "r_collection", "r_references", "r_multipassage", "r_register"
    ]

    OPEN_COLLECTIONS = ["Formulae Mondseer"]

    def __init__(self, *args, **kwargs):
        if "pdf_folder" in kwargs:
            self.pdf_folder = kwargs["pdf_folder"]
            del kwargs["pdf_folder"]
        super(NemoFormulae, self).__init__(*args, **kwargs)
        self.app.jinja_env.filters["remove_from_list"] = self.f_remove_from_list
        self.app.jinja_env.filters["join_list_values"] = self.f_join_list_values

    def f_remove_from_list(self, l, i):
        """ remove item "i" from list "l"

        :param l: the list
        :param i: the item
        :return: the list without the item
        """
        l.remove(i)
        return l

    def f_join_list_values(self, l, s):
        """ join the values of "l" user the separator "s"

        :param l: the list of values
        :param s: the separator
        :return: a string of the values joined by the separator
        """
        return s.join(l)

    def view_maker(self, name, instance=None):
        """ Create a view

        :param name: Name of the route function to use for the view.
        :type name: str
        :return: Route function which makes use of Nemo context (such as menu informations)
        :rtype: function
        """
        # Avoid copy-pasta and breaking upon Nemo inside code changes by reusing the original view_maker function
        # Super will go to the parent class and you will use it's "view_maker" function
        route = super(NemoFormulae, self).view_maker(name, instance)
        if name in self.PROTECTED:
            route = login_required(route)
        return route

    def r_add_text_collections(self, objectIds, reffs, lang=None):
        """ Retrieve the top collections of the inventory

        :param lang: Lang in which to express main data
        :type lang: str
        :return: Collections information and template
        :rtype: {str: Any}
        """
        collection = self.resolver.getMetadata()
        return {
            "template": "main::add_text.html",
            "current_label": collection.get_label(lang),
            "collections": {
                "members": self.make_members(collection, lang=lang)
            },
            "prev_texts": objectIds,
            "prev_reffs": reffs
        }

    def r_add_text_collection(self, objectId, objectIds, reffs, lang=None):
        """ Route to browse collections and add another text to the view

        :param objectId: Collection identifier
        :type objectId: str
        :param lang: Lang in which to express main data
        :type lang: str
        :return: Template and collections contained in given collection
        :rtype: {str: Any}
        """
        collection = self.resolver.getMetadata(objectId)
        return {
            "template": "main::add_text.html",
            "collections": {
                "current": {
                    "label": str(collection.get_label(lang)),
                    "id": collection.id,
                    "model": str(collection.model),
                    "type": str(collection.type),
                },
                "members": self.make_members(collection, lang=lang),
                "parents": self.make_parents(collection, lang=lang)
            },
            "prev_texts": objectIds,
            "prev_reffs": reffs
        }

    def r_passage(self, objectId, subreference, lang=None):
        """ Retrieve the text of the passage

        :param objectId: Collection identifier
        :type objectId: str
        :param lang: Lang in which to express main data
        :type lang: str
        :param subreference: Reference identifier
        :type subreference: str
        :return: Template, collections metadata and Markup object representing the text
        :rtype: {str: Any}
        """
        pdf_path = ''
        collection = self.get_collection(objectId)
        if isinstance(collection, CtsWorkMetadata):
            editions = [t for t in collection.children.values() if isinstance(t, CtsEditionMetadata)]
            if len(editions) == 0:
                raise UnknownCollection("This work has no default edition")
            return redirect(url_for(".r_passage", objectId=str(editions[0].id), subreference=subreference))
        text = self.get_passage(objectId=objectId, subreference=subreference)
        passage = self.transform(text, text.export(Mimetypes.PYTHON.ETREE), objectId)
        if 'notes' in self._transform:
            notes = self.extract_notes(passage)
        else:
            notes = ''
        prev, next = self.get_siblings(objectId, subreference, text)
        if current_user.project_team is False and str(text.get_creator(lang)) not in self.OPEN_COLLECTIONS:
            pdf_path = self.pdf_folder + objectId.split(':')[-1] + '.pdf'
        return {
            "template": "main::text.html",
            "objectId": objectId,
            "subreference": subreference,
            "collections": {
                "current": {
                    "label": collection.get_label(lang),
                    "id": collection.id,
                    "model": str(collection.model),
                    "type": str(collection.type),
                    "author": text.get_creator(lang),
                    "title": text.get_title(lang),
                    "description": text.get_description(lang),
                    "citation": collection.citation,
                    "coins": self.make_coins(collection, text, subreference, lang=lang)
                },
                "parents": self.make_parents(collection, lang=lang)
            },
            "text_passage": Markup(passage),
            "notes": Markup(notes),
            "prev": prev,
            "next": next,
            "pdf_path": pdf_path
        }

    def r_multipassage(self, objectIds, subreferences, lang=None):
        """ Retrieve the text of the passage

        :param objectIds: Collection identifiers separated by '+'
        :type objectIds: str
        :param lang: Lang in which to express main data
        :type lang: str
        :param subreference: Reference identifier
        :type subreference: str
        :return: Template, collections metadata and Markup object representing the text
        :rtype: {str: Any}
        """
        ids = objectIds.split('+')
        passage_data = {'template': 'main::multipassage.html', 'objects': []}
        subrefers = subreferences.split('+')
        for i, id in enumerate(ids):
            d = self.r_passage(id, subrefers[i], lang=lang)
            del d['template']
            passage_data['objects'].append(d)
        return passage_data

    def r_login(self):
        """ login form

        :return: template, page title, form
        :rtype: {str: Any}
        """
        if current_user.is_authenticated:
            return redirect(url_for('.r_index'))
        form = LoginForm()
        if form.validate_on_submit():
            user = User.query.filter_by(username=form.username.data).first()
            if user is None or not user.check_password(form.password.data):
                flash('Invalid username or password')
                return redirect(url_for('.r_login'))
            login_user(user, remember=form.remember_me.data)
            next_page = request.args.get('next')
            if not next_page or url_parse(next_page).netloc != '':
                return redirect(url_for('.r_index'))
            return redirect(next_page)
        return {'template': 'main::login.html', 'title': 'Sign In', 'form': form}

    def r_logout(self):
        """ user logout

        :return: redirect to login page
        """
        logout_user()
        return redirect(url_for('.r_login'))

    def r_user(self, username):
        """ profile page for user. Initially used to change user information (e.g., password, email, etc.)

        :return: template, page title, form
        :rtype: {str: Any}
        """
        form = PasswordChangeForm()
        if form.validate_on_submit():
            user = User.query.filter_by(username=username).first_or_404()
            if not user.check_password(form.old_password.data):
                flash("This is not your existing password.")
                return redirect(url_for('.r_user'))
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()
            flash("You have successfully changed your password.")
            return redirect(url_for('.r_login'))
        return {'template': "main::register.html", "title": "Register", "form": form, "username": username}

    def extract_notes(self, text):
        """ Constructs a dictionary that contains all notes with their ids. This will allow the notes to be
        rendered anywhere on the page and not only where they occur in the text.

        :param text: the string to be transformed
        :return: dict('note_id': 'note_content')
        """
        with open(self._transform['notes']) as f:
            xslt = etree.XSLT(etree.parse(f))
        return str(xslt(etree.fromstring(text)))