"""Avisar sobre un resguardo fallido usando el canal de correo existente."""
from datetime import UTC, datetime
import os
from uuid import UUID, NAMESPACE_URL, uuid5

from deliver_reminder_email import mailbox, ResendSender
from reminder_email import ReminderEmail


def main():
    source = os.environ['GITHUB_SERVER_URL'] + '/' + os.environ['GITHUB_REPOSITORY']
    link = source + '/actions/runs/' + os.environ['GITHUB_RUN_ID']
    recipient = mailbox(os.environ['PIGGO_BACKUP_ALERT_EMAIL'])
    sender = ResendSender(os.environ['RESEND_API_KEY'], os.environ['PIGGO_BACKUP_FROM_EMAIL'])
    message = ReminderEmail(UUID(int=0), UUID(int=0), datetime.now(UTC).date(),
                            'Falló el resguardo semanal de Piggo',
                            'Revisá la ejecución del resguardo de Piggo:\n' + link)
    outcome = sender.send(uuid5(NAMESPACE_URL, link + '/backup-failed'), recipient, message)
    if outcome.estado != 'aceptada':
        raise RuntimeError('El proveedor no confirmó el aviso de fallo')


if __name__ == '__main__':
    main()
