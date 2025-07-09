from django import template
import pprint

register = template.Library()

@register.filter
def pprint(value):
    """Pretty print filter for debugging in templates"""
    return pprint.pformat(value)
