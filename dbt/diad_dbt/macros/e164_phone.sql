{% macro e164_phone(raw_phone) %}
regexp_replace({{ raw_phone }}, r'[^0-9+]', '')
{% endmacro %}
