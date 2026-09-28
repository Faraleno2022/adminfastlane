from django.contrib.auth.models import AnonymousUser
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase

from core.models import Entreprise, Poste
from employes.forms import EmployeForm


class EmployeFormCreationTests(TestCase):
    def setUp(self):
        self.entreprise = Entreprise.objects.create(
            nom_entreprise="Entreprise desktop de test",
            slug="entreprise-desktop-test",
            email="desktop@example.com",
        )
        self.donnees_minimales = {
            "nom": "Camara",
            "prenoms": "Aminata",
            "nombre_femmes": "0",
            "mode_paiement": "virement",
        }

    def test_creation_possible_si_aucun_poste_n_est_configure(self):
        form = EmployeForm(
            data=self.donnees_minimales,
            entreprise=self.entreprise,
        )

        self.assertFalse(form.fields["poste"].required)
        self.assertTrue(form.is_valid(), form.errors.as_json())

    def test_poste_requis_des_qu_un_choix_est_disponible(self):
        Poste.objects.create(
            entreprise=self.entreprise,
            code_poste="RH01",
            intitule_poste="Responsable RH",
        )
        form = EmployeForm(
            data=self.donnees_minimales,
            entreprise=self.entreprise,
        )

        self.assertTrue(form.fields["poste"].required)
        self.assertFalse(form.is_valid())
        self.assertIn("poste", form.errors)

    def test_barre_fixe_utilise_un_bouton_dans_le_formulaire(self):
        request = RequestFactory().get("/employes/create/")
        request.user = AnonymousUser()
        html = render_to_string(
            "employes/form.html",
            {
                "form": EmployeForm(entreprise=self.entreprise),
                "object": None,
            },
            request=request,
        )

        form_start = html.index('<form method="post"')
        form_end = html.index("</form>", form_start)
        fixed_bar = html.index("fixed-bottom", form_start)

        self.assertLess(fixed_bar, form_end)
        self.assertIn("novalidate", html[form_start:form_end])
        self.assertNotIn('form="employe-form"', html)
