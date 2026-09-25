# Provisión de Absolut Cinema en AWS

Configuración de VPC, EC2, IAM, S3 y SES. Todo corre en una sola instancia con SQLite (`data/snapshots.db` de la captura y
`data/app.db` de las cuentas); el plan con PostgreSQL en RDS se descartó el 2026-09-25 por costo (ver `project.md`).

## Decisiones previas

- **Región:** us-east-1 (más opciones t4g, más barato).
- **Zona horaria:** America/Mexico_City (configurar en EC2).
- **Base de datos:** SQLite en el disco de la instancia; sin RDS.
- **Backup:** `deploy/backup.sh` diario al bucket S3 (copias en línea de ambas bases y el crudo) más snapshots de EBS.

---

## 1. VPC y Red

### Red

```
VPC: 10.0.0.0/16 (cualquier /16 privado)
  ├─ Subnet privada AZ-1 (EC2): 10.0.1.0/24
  └─ NAT Gateway en subnet pública para salidas (EC2 → APIs externas)
```

Salida hacia Cinépolis: su WAF de Cloudflare bloquea los rangos de AWS por ASN, así que ni la IP elástica ni el NAT
Gateway sirven para `api-g.cinepolis.com` (verificado 2026-09-10). Lo resuelve el cliente WARP de Cloudflare dentro de la
instancia (modo proxy + Privoxy), que instala `deploy/install.sh`; el security group solo necesita salida 443 y UDP hacia
Cloudflare (WARP usa MASQUE sobre UDP 443 y cae a TCP si no puede). Cinemex, Rappi y DiDi salen directo.

### Pasos en AWS Console

1. **VPC → Crear VPC:**
   - Nombre: `absolut-cinema`
   - CIDR: `10.0.0.0/16`
   - DNS habilitado (✓)

2. **Subnets privadas:**
   - `absolut-ec2-1a`: `10.0.1.0/24`, AZ `us-east-1a`

3. **Subnet pública (opcional, solo para NAT):**
   - `absolut-public-1a`: `10.0.100.0/24`, AZ `us-east-1a`
   - → Internet Gateway + NAT Gateway

4. **Route table privada:**
   - EC2 sale por NAT: `0.0.0.0/0` → NAT Gateway en subnet pública

---

## 2. Security Groups

### SG para EC2 (`absolut-ec2`)

```
Inbound:
  ├─ SSH (22) ← tu IP fija (o 0.0.0.0/0 con básico, luego SSH key)
  ├─ Streamlit (8501) ← NLB / Cloudflare / tu IP (no exponer directo)
  └─ —

Outbound:
  └─ Cualquiera a internet (443, 80) para APIs Cinépolis/Cinemex
```

### Pasos en AWS Console

1. **VPC → Security Groups → Crear SG:**
   - Nombre: `absolut-ec2`
   - VPC: `absolut-cinema`
   - Inbound:
     - SSH 22 desde tu IP
     - TCP 8501 desde 0.0.0.0/0 (después restringir)
   - Outbound: todo (default)


---

## 3. IAM: Role y Policy para EC2

### Permisos necesarios

EC2 necesita:
- **S3:** leer y escribir en bucket de respaldos (`backup.timer` → `s3://absolut-cinema-{account}/raw/` y `snapshots/`).
- **CloudWatch:** escribir logs opcionales.
- **SES:** enviar los correos de invitación y restablecimiento de contraseña del dashboard (`AC_MAIL_BACKEND=ses`,
  2026-09-10), solo desde el remitente del dominio.

### Policy JSON (`absolut-cinema-ec2-policy`)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::absolut-cinema-backup",
        "arn:aws:s3:::absolut-cinema-backup/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:us-east-1:*:*"
    },
    {
      "Effect": "Allow",
      "Action": ["ses:SendEmail", "ses:SendRawEmail"],
      "Resource": "arn:aws:ses:us-east-1:CUENTA:identity/DOMINIO",
      "Condition": { "StringLike": { "ses:FromAddress": "*@DOMINIO" } }
    }
  ]
}
```

### Pasos en AWS Console

1. **IAM → Roles → Crear role:**
   - Entidad de confianza: `EC2`
   - Nombre: `absolut-cinema-ec2-role`

2. **Adjuntar policy:**
   - Crear inline policy con el JSON arriba
   - O crear policy gestionada y adjuntarla

3. **Crear instance profile:**
   - Nombre: `absolut-cinema-ec2-instance-profile`
   - Rol: `absolut-cinema-ec2-role`

---

## 4. EC2: Instancia de la aplicación

### Configuración

```
AMI: Ubuntu 22.04 LTS (Canonical, arm64 t4g compatible)
Instance type: t4g.small (2 GB; ver docs/ec2-sizing.md)
Storage: EBS gp3 30 GB (la base crece ~22–27 GB al año sin retención de `event`)
VPC: absolut-cinema
Subnet: absolut-ec2-1a (privada)
Security Group: absolut-ec2
IAM Instance Profile: absolut-cinema-ec2-instance-profile
Monitoring: detailed CloudWatch
Tenancy: default
```

### Pasos en AWS Console

1. **EC2 → Lanzar instancia:**
   - Nombre: `absolut-cinema-app`
   - AMI: `Ubuntu 22.04 LTS` (búscar `arm64`)
   - Type: `t4g.medium`
   - Key pair: crear o usar existente (`absolut-cinema.pem` → guardar localmente)
   - VPC: `absolut-cinema`
   - Subnet: `absolut-ec2-1a`
   - Auto-assign public IP: no
   - IAM instance profile: `absolut-cinema-ec2-instance-profile`
   - Monitoreo: CloudWatch detallado ✓

2. **Storage:**
   - Root: gp3 30 GB
   - Encrypted: sí (AWS-managed)
   - Borrar al terminar: sí (por defecto)

3. **Security Group:** `absolut-ec2`

4. **Tags:**
   ```
   Name: absolut-cinema-app
   Project: absolut-cinema
   Environment: production
   ```

5. **Lanzar**, esperar estado `running`, copiar dirección IP privada (ej. `10.0.1.42`)

### Post-lanzamiento

```bash
# Conectar (requiere vpn a vpc o NAT bastion)
ssh -i absolut-cinema.pem ubuntu@10.0.1.42

# Configurar servidor
sudo bash deploy/install.sh
# (install.sh va a:)
#   - Python 3.12 y el venv del dashboard
#   - Repositorio absolut-cinema en /opt/absolut-cinema
#   - Systemd units en /etc/systemd/system/
#   - Timers generados desde jobs/registry.py (deploy/systemd/): snapshot, seats, health, etc.
#   - Caddy (HTTPS + basic auth)
#   - Cloudflare WARP (modo proxy, SOCKS5 :40000) + Privoxy (HTTP :8118) para salir hacia Cinépolis
#   - .env: AC_EGRESS_PROXY=http://127.0.0.1:8118, CINEPOLIS_API_KEY, CINEMEX_CONSUMER_KEY
```

---

## 5. S3: Respaldos

### Bucket

```
Nombre: absolut-cinema-backup-{account-id}
Region: us-east-1
Versionado: habilitado
Cifrado: AES-256 (default)
ACL: privado (bucket owner full control)
```

### Estructura de carpetas

```
s3://absolut-cinema-backup-{account}/
├─ raw/{chain}/{date}/*.json.gz (crudo de snapshots)
├─ db/ (snapshots.db diarios, comprimidos)
├─ app/ (app.db diarios: cuentas y sesiones)
└─ logs/ (run.log de cada respaldo)
```

### Lifecycle Policy

```json
{
  "Rules": [
    {
      "Id": "delete-old-raw",
      "Status": "Enabled",
      "Filter": { "Prefix": "raw/" },
      "Expiration": { "Days": 30 }
    },
    {
      "Id": "delete-old-snapshots",
      "Status": "Enabled",
      "Filter": { "Prefix": "snapshots/" },
      "Expiration": { "Days": 60 }
    }
  ]
}
```

### Pasos en AWS Console

1. **S3 → Crear bucket:**
   - Nombre: `absolut-cinema-backup-{tu-account-id}`
   - Region: us-east-1
   - ACL deshabilitado (recomendado)
   - Versionado: habilitado

2. **Propiedades → Cifrado:** AES-256 (default)

3. **Permisos → Bucket Policy:** (ya está en IAM policy de EC2 arriba)

4. **Ciclo de vida:**
   - Añadir regla de expiración para `raw/` (30 días) y `snapshots/` (60 días)

---

## 6. Credenciales y secretos

### Archivo: `deploy/absolut-cinema.env`

Nunca commitear, reemplazar valores:

```bash
# APIs externas (del bundle JS de cada sitio)
CINEPOLIS_API_KEY=lQM6Mkvri1iHksKKCfpAiwGXq0YUZA7Nn6XAXRPr4i13LwXo
CINEMEX_CONSUMER_KEY=XXQha7vz4kdvoMSdixhN
CINEMEX_BASE_URL=https://api.cinemex.com/rest/v2.38/

# Acceso al dashboard: cuentas en data/app.db (se crea sola), correo por SES y URL pública para los enlaces
AC_MAIL_BACKEND=ses
AC_MAIL_FROM=Absolut Cinema <no-responder@DOMINIO>
AC_BASE_URL=https://DOMINIO

# S3
AWS_REGION=us-east-1
BACKUP_BUCKET=absolut-cinema-backup-123456789

# Streamlit (basic auth tras Caddy HTTPS)
STREAMLIT_SERVER_HEADLESS=true
STREAMLIT_SERVER_PORT=8501
STREAMLIT_SERVER_ADDRESS=127.0.0.1

# Zona horaria
TZ=America/Mexico_City
```

### Amazon SES: correo de invitación y restablecimiento (2026-09-10)

El dashboard manda dos correos transaccionales (invitación al crear una cuenta, enlace de restablecimiento) con
`boto3` y las credenciales del rol de la instancia; no hay credenciales SMTP.

1. **SES → Identities → Create identity → Domain**: el dominio que se compre para el dashboard. Elegir *Easy DKIM* y
   publicar los tres registros CNAME en el DNS (misma zona que apunta a la IP de Caddy). Opcional: *custom MAIL FROM*
   (`correo.DOMINIO`, registros MX y TXT) para alinear SPF.
2. **Sandbox**: una cuenta nueva de SES solo entrega a direcciones verificadas y hasta 200 correos al día. Para el
   piloto basta verificar a mano los correos del personal de Cinemex (**Identities → Create identity → Email**); para
   abrirlo, **Account dashboard → Request production access** (caso de uso: correos transaccionales de acceso a un
   tablero interno, menos de 100 al mes, sin listas).
3. **IAM**: el statement de `ses:SendEmail` de la sección 3, acotado a la identidad del dominio y al remitente.
4. **Servidor**: `AC_MAIL_BACKEND=ses`, `AC_MAIL_FROM`, `AWS_REGION` y `AC_BASE_URL=https://DOMINIO` en
   `/etc/absolut-cinema.env`; `systemctl restart absolut-cinema-dashboard`; probar con `make user-reset EMAIL=…`.

Mientras no haya dominio, `AC_MAIL_BACKEND=console` deja cada correo en `data/logs/mail.log` y el admin entrega el enlace
por otro canal (`make user-create … NOMAIL=1`).

### Gestión de secretos

- **EC2:** copiar `.env` a `/opt/absolut-cinema/.env` (permisos 600).
- **Alternativa con Secrets Manager:** 
  ```bash
  aws secretsmanager create-secret --name absolut-cinema/db-password \
    --secret-string "PASSWORD_FUERTE"
  ```
  Después readaptálo en `deploy/install.sh`.

---

## 7. Monitoreo y alertas

### CloudWatch

```
Métricas de EC2:
  ├─ CPU Utilization (alertar si > 80%)
  ├─ Memory (cloudwatch-agent, alertar si > 80%)
  └─ Disk (cloudwatch-agent, alertar si > 85%)

Logs:
  ├─ /var/log/absolut-cinema/run.log (scraper)
  ├─ /var/log/absolut-cinema/health.log (health check)
  └─ /var/log/caddy/caddy.log (Streamlit)
```

### SNS Alerts (opcional)

```
Topic: absolut-cinema-alerts
Suscriptores: tu email, Slack
Condiciones:
  - EC2 CPU > 80% por 5 min
  - health.log indica "problems"
```

---

## 8. Checklist de post-lanzamiento

### Seguridad
- [ ] SSH key guardada localmente en `~/.ssh/absolut-cinema.pem` (permisos 600)
- [ ] IAM policy restringida (solo S3 + logs, sin EC2DescribeInstances)

### Operación
- [ ] `deploy/install.sh` ejecutado sin errores
- [ ] Timers arrancados: `systemctl list-timers`
- [ ] Primer snapshot capturado: `ls -la /opt/absolut-cinema/data/snapshots.db`
- [ ] Dashboard accesible en `https://absolut-cinema.ejemplo.com` (Caddy + basic auth)
- [ ] Logs en CloudWatch aparecen

### Respaldos
- [ ] Bucket S3 creado y accesible desde EC2
- [ ] Primer backup en S3: `aws s3 ls s3://absolut-cinema-backup-*/`
- [ ] Ciclo de vida configurado

---

## Costos estimados

| Componente | Especificación | Costo/mes USD |
| --- | --- | --- |
| EC2 | t4g.small on-demand | 12.26 |
| EBS | 30 GB gp3 | 2.40 |
| S3 | respaldos + storage | 3.00 |
| NAT Gateway | tráfico + uso | 5.00 |
| CloudWatch | basic logs | 1.00 |
| **Total** | | **~23.66 USD/mes** |

Sin RDS: el db.t4g.micro multi-AZ (~22.50 USD/mes) era casi la mitad del costo y no hacía falta para este volumen
(decisión 2026-09-25).

(Precios us-east-1, on-demand. Reserved instances reducen ~25%.)

---

## Referencias

- VPC: https://docs.aws.amazon.com/vpc/
- EC2 IAM: https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/iam-roles-for-amazon-ec2.html
- `deploy/install.sh`: revisa qué paquetes y servicios instala
