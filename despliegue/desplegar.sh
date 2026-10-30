#!/bin/bash
# Publica (o actualiza) el inventario en inventario.serenaesteve.com. Se puede lanzar las veces que haga falta.
#   sudo bash despliegue/desplegar.sh
set -euo pipefail

DOMINIO=inventario.serenaesteve.com
IP_SERVIDOR=82.165.244.40
ORIGEN=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
DIR_DESPLIEGUE=$ORIGEN/despliegue

# 1. Usuario propio, sin acceso al sistema ni a los datos de los demás servicios
id inventario >/dev/null 2>&1 || useradd --system --home-dir /srv/inventario --shell /usr/sbin/nologin inventario
install -d -o root -g inventario -m 750 /srv/inventario
install -d -o inventario -g inventario -m 750 /srv/inventario/datos
install -d -o root -g inventario -m 750 /srv/inventario/app

# 2. El código: de root y solo lectura para el servicio. Los datos no se tocan
rsync -a --delete --exclude '.git/' --exclude 'datos/' --exclude '__pycache__/' --exclude '*.pyc' \
  --chown=root:inventario --chmod=D750,F640 "$ORIGEN/" /srv/inventario/app/

# 3. El servicio
install -m 644 "$DIR_DESPLIEGUE/inventario.service" /etc/systemd/system/inventario.service
systemctl daemon-reload
systemctl enable inventario.service >/dev/null 2>&1
systemctl restart inventario.service
sleep 4
systemctl is-active inventario.service
echo "Servicio: $(curl -s -o /dev/null -m 5 -w '%{http_code}' http://127.0.0.1:8095/login.html) en /login.html"

# 4. Apache en el puerto 80 (redirección a HTTPS y verificación de Let's Encrypt)
install -m 644 "$DIR_DESPLIEGUE/inventario.conf" /etc/apache2/sites-available/inventario.conf
a2ensite -q inventario.conf

# 5. HTTPS, solo cuando el DNS apunte a este servidor. Se pregunta a un DNS público, que es lo que ve
#    Let's Encrypt: el DNS local de este servidor puede tardar horas en olvidar la dirección antigua
IP_DOMINIO=$(dig +short A "$DOMINIO" @1.1.1.1 | tail -1)
IPV6_DOMINIO=$(dig +short AAAA "$DOMINIO" @1.1.1.1 | tail -1)
if [ "$IP_DOMINIO" != "$IP_SERVIDOR" ] || [ -n "$IPV6_DOMINIO" ]; then
  apache2ctl -t 2>&1 | tail -1
  systemctl reload apache2
  echo
  echo "FALTA EL DNS: $DOMINIO apunta a ${IP_DOMINIO:-nada}${IPV6_DOMINIO:+ y a la IPv6 $IPV6_DOMINIO}."
  echo "Tiene que tener un registro A con $IP_SERVIDOR y ningún registro AAAA."
  echo "Cuando lo cambies, vuelve a lanzar este script: sacará el certificado y publicará el HTTPS."
  exit 0
fi

apache2ctl -t 2>&1 | tail -1
systemctl reload apache2
if [ ! -e "/etc/letsencrypt/live/$DOMINIO/fullchain.pem" ]; then
  certbot certonly --webroot -w /var/www/acme -d "$DOMINIO" --non-interactive --keep-until-expiring \
    --deploy-hook "systemctl reload apache2"
fi
install -m 644 "$DIR_DESPLIEGUE/inventario-ssl.conf" /etc/apache2/sites-available/inventario-ssl.conf
a2ensite -q inventario-ssl.conf
apache2ctl -t 2>&1 | tail -1
systemctl reload apache2
sleep 1
echo "Publicado: https://$DOMINIO → $(curl -s -o /dev/null -m 10 --resolve "$DOMINIO:443:$IP_SERVIDOR" -w '%{http_code}' "https://$DOMINIO/login.html")"
echo "Contraseñas iniciales (si es la primera vez): sudo cat /srv/inventario/datos/credenciales-iniciales.txt"
