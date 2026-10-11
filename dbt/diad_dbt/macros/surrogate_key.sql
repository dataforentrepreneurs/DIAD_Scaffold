{% macro surrogate_key(fields) %}
to_hex(md5(concat({{ fields | join(", ") }})))
{% endmacro %}
