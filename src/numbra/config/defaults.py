_DEFAULT_TOML = """[challenge]
duration_minutes = 6
difficulty = "normal"
stages = 3
operations = ["+", "-", "*", "/"]

[timing]
operation_bonus_enabled = true
[timing.operation_bonus_seconds]
"+" = 0
"-" = 0
"*" = 1
"/" = 2

[stages.fast]
limit_seconds = 5
[stages.normal]
limit_seconds = 10
[stages.slow]
limit_seconds = 15

[difficulties.very-easy]
min_value = 1
max_value = 10
min_terms = 2
max_terms = 2
[difficulties.easy]
min_value = 1
max_value = 20
min_terms = 2
max_terms = 2
[difficulties.normal]
min_value = 2
max_value = 50
min_terms = 2
max_terms = 3
[difficulties.hard]
min_value = 5
max_value = 150
min_terms = 2
max_terms = 3
[difficulties.very-hard]
min_value = 10
max_value = 999
min_terms = 3
max_terms = 4
"""

_DEFAULT_TEMPLATES = '["{left} {operation} {right}"]\n'
_DEFAULT_DESIGN = (
    '[styles]\naccent = "bold cyan"\nsuccess = "green"\nerror = "bold red"\ntimer = "yellow"\n'
)
