"""The mail outbox and the template renderer."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from riso.platform.mail import MailOutboxRow, MailTemplates, OutboxMailSender
from riso.shared import FixedClock, NotFound, UuidV7Generator, ValidationFailed
from riso.shared.ports import MailMessage

CLOCK = FixedClock(datetime(2026, 11, 8, 9, 0, tzinfo=UTC))
MESSAGE = MailMessage(
    to="starosta@example.test",
    subject="Pozvánka do riso",
    body="Dobrý deň,\nboli ste pozvaný.\n",
    template="invitation",
    customer_id="c1",
)


def outbox(session) -> list[MailOutboxRow]:
    return list(session.scalars(select(MailOutboxRow).order_by(MailOutboxRow.created_at)))


def test_a_sent_message_lands_in_the_outbox_with_the_transaction(migrated):
    with migrated.session() as session:
        sender = OutboxMailSender(session, CLOCK, UuidV7Generator(CLOCK))
        message_id = sender.send(MESSAGE)
        session.commit()
    with migrated.session() as session:
        [row] = outbox(session)
    assert row.id == message_id
    assert (row.to_address, row.subject, row.template) == (
        MESSAGE.to,
        MESSAGE.subject,
        "invitation",
    )
    assert row.body == MESSAGE.body
    assert row.created_at == CLOCK.now()
    assert (row.customer_id, row.sent_at, row.attempts) == ("c1", None, 0)


def test_a_rolled_back_change_leaves_no_mail(migrated):
    with migrated.session() as session:
        OutboxMailSender(session, CLOCK, UuidV7Generator(CLOCK)).send(MESSAGE)
        session.rollback()
    with migrated.session() as session:
        assert outbox(session) == []


def test_an_address_without_at_is_refused(migrated):
    with migrated.session() as session, pytest.raises(ValidationFailed):
        OutboxMailSender(session, CLOCK, UuidV7Generator(CLOCK)).send(
            MailMessage(to="nobody", subject="s", body="b", template="t")
        )


# --- templates ---------------------------------------------------------------------------


@pytest.fixture
def templates(tmp_path) -> MailTemplates:
    (tmp_path / "invitation.sk.txt").write_text(
        "Subject: Pozvánka do riso pre $customer\n\n"
        "Dobrý deň,\n\nnastavte si heslo do $expires:\n$link\n",
        encoding="utf-8",
    )
    (tmp_path / "broken.sk.txt").write_text("No subject line here\n", encoding="utf-8")
    return MailTemplates(tmp_path)


def test_a_slovak_template_is_rendered(templates):
    mail = templates.render(
        "invitation", customer="Obec Boldog", expires="15. 11. 2026", link="http://x/t/abc"
    )
    assert mail.subject == "Pozvánka do riso pre Obec Boldog"
    assert mail.body == "Dobrý deň,\n\nnastavte si heslo do 15. 11. 2026:\nhttp://x/t/abc\n"
    message = mail.to("starosta@example.test", customer_id="c1")
    assert (message.template, message.customer_id) == ("invitation", "c1")


def test_a_missing_value_is_an_error(templates):
    with pytest.raises(ValueError, match="no value for link"):
        templates.render("invitation", customer="Obec Boldog", expires="15. 11. 2026")


def test_a_template_without_a_subject_is_an_error(templates):
    with pytest.raises(ValueError, match="Subject"):
        templates.render("broken")


def test_an_unknown_template_is_not_found(templates):
    with pytest.raises(NotFound):
        templates.render("nothing")
