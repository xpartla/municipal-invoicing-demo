"""The shipped Slovak mail templates render with the values their senders give."""

import pytest

from riso.platform.mail import TEMPLATES_DIR, MailTemplates

VALUES = {
    "invitation": {"name": "Jana", "scope": "Obec Boldog", "link": "L", "expires": "E"},
    "access_granted": {"name": "Jana", "scope": "Obec Boldog", "link": "L"},
    "password_reset": {"name": "Jana", "link": "L", "expires": "E"},
    "password_changed": {"name": "Jana", "when": "W", "link": "L"},
    "email_change": {"name": "Jana", "link": "L", "expires": "E"},
    "email_change_notice": {"name": "Jana", "new_email": "N"},
}


def test_every_shipped_template_has_its_values_listed():
    shipped = sorted(p.name.removesuffix(".sk.txt") for p in TEMPLATES_DIR.glob("*.sk.txt"))
    assert shipped == sorted(VALUES)


@pytest.mark.parametrize("name", sorted(VALUES))
def test_each_template_renders_in_slovak(name):
    mail = MailTemplates().render(name, **VALUES[name])
    assert mail.subject and "$" not in mail.subject + mail.body
    assert mail.body.startswith("Dobrý deň, Jana,") and mail.body.endswith("riso\n")
