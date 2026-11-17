"""Provision del rol dedicado: reutiliza el transporte local sin revelar secretos."""
from local_roles import SQL_DIR,run,LocalError


def provision_jobs(database,password):
    if not isinstance(password,str) or len(password)<16 or any(c in password for c in '\n\r\0'):
        raise LocalError('Contraseña de jobs invalida.')
    target='/tmp/gastos-provision-jobs.sql'
    copied=run(['docker','cp',str(SQL_DIR/'provision-jobs.sql'),f'{database.container}:{target}'])
    if copied.returncode:raise LocalError('No se pudo copiar el script de jobs.')
    result=run(['docker','exec','-i',database.container,'psql','-X','--no-password',
        '--set=ON_ERROR_STOP=1','--username','postgres','--dbname','postgres','--file',target],
        data=password+'\n'+password+'\n')
    if result.returncode:
        # Solo el primer diagnostico, sin contexto SQL ni stdin; mismo contrato que local_roles.
        errors=[line.split('ERROR:',1)[1].strip() for line in result.stderr.splitlines() if 'ERROR:' in line]
        detail=errors[0].replace(password,'[REDACTADO]') if errors else 'Revisar permisos administrativos.'
        raise LocalError('La provision de jobs fallo y no se confirmo. '+detail)
