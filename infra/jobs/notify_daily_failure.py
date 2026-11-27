"""Envia al responsable un enlace a la ejecución fallida."""
from datetime import UTC, datetime
import os
import sys
from uuid import NAMESPACE_URL, UUID, uuid5

from deliver_reminder_email import ResendSender, mailbox
from reminder_email import ReminderEmail


def main():
    try:
        recipient = os.environ.get('PIGGO_DAILY_ALERT_EMAIL')
        if not recipient:
            print('Aviso por correo sin destinatario configurado. El fallo quedó registrado en GitHub Actions.')
            return 0
        link = '/'.join((os.environ['GITHUB_SERVER_URL'], os.environ['GITHUB_REPOSITORY'],
                         'actions/runs', os.environ['GITHUB_RUN_ID']))
        sender = ResendSender(os.environ['RESEND_API_KEY'], os.environ['PIGGO_DAILY_FROM_EMAIL'])
        message = ReminderEmail(UUID(int=0), UUID(int=0), datetime.now(UTC).date(),
                                'Falló el proceso diario de Piggo',
                                'Revisá las tareas que fallaron en GitHub Actions:\n' + link)
        attempt = uuid5(NAMESPACE_URL, link + '/daily-failed')
        if sender.send(attempt, mailbox(recipient), message).estado == 'aceptada':
            print('El proveedor aceptó el aviso de fallo.')
            return 0
    except Exception:
        pass
    print('ERROR: no se confirmó el correo de fallo. Revisá la configuración del aviso.', file=sys.stderr)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
