import io
import mimetypes
import smtplib
from email.message import EmailMessage
from typing import List, Optional, Union


class Mailable:
    """Equivalent to the Java Mailable interface/object."""

    def __init__(
        self,
        sender: str,
        recipients: str,
        subject: str,
        message: str,
        ccs: str = None,
        bccs: str = None,
        reply_to: str = None,
    ):
        self.sender = sender
        self.recipients = (
            recipients  # Expected as a string, potentially semicolon separated
        )
        self.subject = subject
        self.message = message
        self.ccs = ccs
        self.bccs = bccs
        self.reply_to = reply_to


class MailServer:
    """Equivalent to the org.webcurator.core.notification.MailServer class."""

    def __init__(self, args):
        """
        :param config: Dictionary containing 'host', 'port', 'user', 'password', 'use_ssl'
        """
        self.args = args

    def _prepare_base_message(self, email: Mailable) -> EmailMessage:
        msg = EmailMessage()
        msg["Subject"] = email.subject
        msg["From"] = email.sender
        msg["To"] = email.recipients.replace(
            ";", ","
        )  # Python prefers comma separation

        if email.ccs:
            msg["Cc"] = email.ccs.replace(";", ",")
        if email.reply_to:
            msg["Reply-To"] = email.reply_to

        # BCCs are added during the send process, not usually in the header
        return msg

    def _send_over_smtp(self, msg: EmailMessage, bccs: Optional[str] = None):
        host = self.args.mail_smtp_host
        port = self.args.mail_smtp_port
        user = None
        password = None

        # Collect all recipients for the SMTP envelope (To + Cc + Bcc)
        all_recipients = [msg["To"]]
        if msg["Cc"]:
            all_recipients.append(msg["Cc"])
        if bccs:
            all_recipients.extend(bccs.split(";"))

        # Standard connection logic
        with smtplib.SMTP(host, port) as server:
            # if self.args.get("use_tls"):
            server.starttls()
            if user and password:
                server.login(user, password)
            server.send_message(msg, from_addr=msg.get("From"), to_addrs=msg.get("To"))

    def send(
        self,
        email: Mailable,
        filename: str = None,
        mime_type: str = None,
        file_content: Union[str, bytes, io.BytesIO] = None,
    ):
        """Equivalent to Java send(Mailable email) and send with attachments."""
        msg = self._prepare_base_message(email)
        msg.set_content(email.message)

        if file_content:
            # Handle attachment logic
            if isinstance(file_content, io.BytesIO):
                data = file_content.getvalue()
            elif isinstance(file_content, str):
                data = file_content.encode("utf-8")
            else:
                data = file_content

            maintype, subtype = (mime_type or "application/octet-stream").split("/", 1)
            msg.add_attachment(
                data, maintype=maintype, subtype=subtype, filename=filename
            )

        self._send_over_smtp(msg, email.bccs)

    def send_html(self, email: Mailable):
        """Equivalent to Java sendHTML(Mailable email)."""
        msg = self._prepare_base_message(email)

        # Create 'alternative' structure (Text + HTML)
        msg.set_content(email.message)  # Plain text version
        msg.add_alternative(email.message, subtype="html")  # HTML version

        self._send_over_smtp(msg, email.bccs)
