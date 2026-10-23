from django import template

from ventes.templatetags.ventes_extras import gnf

register = template.Library()
register.filter("gnf", gnf)
