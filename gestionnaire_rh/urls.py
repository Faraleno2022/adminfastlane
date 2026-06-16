"""
URL configuration for gestionnaire_rh project.
"""
from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import TemplateView
from django.views.static import serve
from django.http import HttpResponse
from core.views_modules.demo import demo_accueil, demo_telecharger_pdf
import os

def robots_txt(request):
    content = """# Robots.txt pour GuinéeRH
User-agent: *
Allow: /
Allow: /login/
Allow: /inscription/
Disallow: /admin/
Disallow: /api/
Disallow: /employes/
Disallow: /paie/
Disallow: /conges/
Disallow: /core/
Disallow: /comptabilite/
Sitemap: https://www.guineerh.space/sitemap.xml
"""
    return HttpResponse(content, content_type="text/plain")

def sitemap_xml(request):
    content = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    <url>
        <loc>https://www.guineerh.space/</loc>
        <changefreq>weekly</changefreq>
        <priority>1.0</priority>
    </url>
    <url>
        <loc>https://www.guineerh.space/login/</loc>
        <changefreq>monthly</changefreq>
        <priority>0.9</priority>
    </url>
    <url>
        <loc>https://www.guineerh.space/inscription/</loc>
        <changefreq>monthly</changefreq>
        <priority>0.8</priority>
    </url>
    <url>
        <loc>https://www.guineerh.space/documentation-legale/</loc>
        <changefreq>monthly</changefreq>
        <priority>0.8</priority>
    </url>
</urlset>"""
    return HttpResponse(content, content_type="application/xml")

def google_verification(request):
    return HttpResponse("google-site-verification: google47b11a2550ab2dda.html", content_type="text/html")

def google_verification_2(request):
    return HttpResponse("google-site-verification: google10babad53f3eade7.html", content_type="text/html")

urlpatterns = [
    # Démonstration commerciale (accessible sans authentification)
    path('demo/', demo_accueil, name='demo_accueil'),
    path('demo/pdf/', demo_telecharger_pdf, name='demo_telecharger_pdf'),

    path('robots.txt', robots_txt, name='robots_txt'),
    path('sitemap.xml', sitemap_xml, name='sitemap_xml'),
    path('google47b11a2550ab2dda.html', google_verification, name='google_verification'),
    path('google10babad53f3eade7.html', google_verification_2, name='google_verification_2'),
    path('gestion-admin-rh/', admin.site.urls),
    path('', include('core.urls')),
    path('dashboard/', include('dashboard.urls')),
    path('employes/', include('employes.urls')),
    path('paie/', include('paie.urls')),
    path('temps/', include('temps_travail.urls')),
    path('conges/', include('conges.urls')),
    path('recrutement/', include('recrutement.urls')),
    path('formation/', include('formation.urls')),
    path('payments/', include('payments.urls')),
    path('portail/', include('portail.urls')),
    path('comptabilite/', include('comptabilite.urls')),
    path('secretariat/', include('secretariat.urls')),
    path('stock/', include('stock.urls')),
    path('contrats/', include('contrats.urls')),
    # path('api/', include('api.urls')),  # TODO: Create api app
]

# Servir les fichiers statiques et media (nécessaire pour PyInstaller)
def serve_static(request, path):
    import sys
    from pathlib import Path
    if getattr(sys, 'frozen', False):
        # En mode PyInstaller, utiliser le dossier de l'exécutable
        base = Path(os.path.dirname(sys.executable))
    else:
        base = settings.BASE_DIR
    document_root = str(base / 'static')
    return serve(request, path, document_root=document_root)

def serve_media(request, path):
    import sys
    from pathlib import Path
    if getattr(sys, 'frozen', False):
        base = Path(os.path.dirname(sys.executable))
    else:
        base = settings.BASE_DIR
    document_root = str(base / 'media')
    return serve(request, path, document_root=document_root)

urlpatterns += [
    re_path(r'^static/(?P<path>.*)$', serve_static),
    re_path(r'^media/(?P<path>.*)$', serve_media),
]

# Customisation de l'admin
admin.site.site_header = "Gestionnaire RH Guinée"
admin.site.site_title = "Administration RH"
admin.site.index_title = "Bienvenue dans l'administration RH"
