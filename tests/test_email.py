from agent.delivery.email import send_email


class FakeSMTP:
    instances = []

    def __init__(self, host, port, timeout=None):
        self.host, self.port, self.sent, self.logged_in = host, port, [], None
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def login(self, user, password):
        self.logged_in = (user, password)

    def send_message(self, msg):
        self.sent.append(msg)


def set_env(monkeypatch, **extra):
    for key in ("SMTP_HOST", "SMTP_PORT", "MAIL_TO"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("SMTP_USER", "myid")
    monkeypatch.setenv("SMTP_PASSWORD", "app-pass")
    monkeypatch.setenv("MAIL_FROM", "myid@naver.com")
    for key, value in extra.items():
        monkeypatch.setenv(key, value)


def test_send_email_defaults_to_naver(monkeypatch):
    set_env(monkeypatch)
    send_email("제목", "<p>본문</p>", smtp_factory=FakeSMTP)
    smtp = FakeSMTP.instances[-1]
    assert (smtp.host, smtp.port) == ("smtp.naver.com", 465)
    assert smtp.logged_in == ("myid", "app-pass")
    msg = smtp.sent[0]
    assert msg["From"] == "myid@naver.com"
    assert msg["To"] == "myid@naver.com" and msg["Subject"] == "제목"
    assert "<p>본문</p>" in msg.get_body(("html",)).get_content()


def test_send_email_custom_server_and_recipient(monkeypatch):
    set_env(monkeypatch, SMTP_HOST="smtp.gmail.com", SMTP_PORT="465", MAIL_TO="other@example.com")
    send_email("제목", "<p>x</p>", smtp_factory=FakeSMTP)
    smtp = FakeSMTP.instances[-1]
    assert smtp.host == "smtp.gmail.com"
    assert smtp.sent[0]["To"] == "other@example.com"
