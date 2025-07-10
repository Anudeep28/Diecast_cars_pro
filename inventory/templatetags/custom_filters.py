from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """
    Template filter to get an item from a dictionary using a key that may contain special characters.
    Usage: {{ my_dict|get_item:'key-with-special/chars' }}
    """
    return dictionary.get(key, 0)
