# Provisión de Absolut Cinema en AWS

Configuración de VPC, EC2, RDS, IAM y S3 para ambos planes (SQLite local → PostgreSQL en RDS).

## Decisiones previas

- **Región:** us-east-1 (más opciones t4g, más barato).
- **Zona horaria:** America/Mexico_City (configurar en EC2 y RDS).
- **Modelo de BD:** plan 1 = SQLite local; plan 2 = RDS PostgreSQL (reemplaza SQLite, scraper → RDS).
- **Backup:** EBS snapshots (plan 1) → RDS automated + S3 (plan 2).

---

## 1. VPC y Red

### Red (recomendado para plan 2)

```
VPC: 10.0.0.0/16 (cualquier /16 privado)
  ├─ Subnet privada AZ-1 (EC2): 10.0.1.0/24
  ├─ Subnet privada AZ-2 (RDS standby): 10.0.2.0/24
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
   - `absolut-rds-1b`: `10.0.2.0/24`, AZ `us-east-1b`

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
  ├─ Cualquiera a RDS (5432, destino SG de RDS)
  └─ Cualquiera a internet (443, 80) para APIs Cinépolis/Cinemex
```

### SG para RDS (`absolut-rds`)

```
Inbound:
  └─ PostgreSQL (5432) ← EC2 SG (absolut-ec2)

Outbound:
  └─ Ninguno requerido (RDS no inicia conexiones hacia fuera)
```

### Pasos en AWS Console

1. **VPC → Security Groups → Crear SG:**
   - Nombre: `absolut-ec2`
   - VPC: `absolut-cinema`
   - Inbound:
     - SSH 22 desde tu IP
     - TCP 8501 desde 0.0.0.0/0 (después restringir)
   - Outbound: todo (default)

2. **Crear SG para RDS:**
   - Nombre: `absolut-rds`
   - Inbound: PostgreSQL 5432 desde `absolut-ec2` SG
   - Outbound: ninguno

---

## 3. IAM: Role y Policy para EC2

### Permisos necesarios

EC2 necesita:
- **S3:** leer y escribir en bucket de respaldos (`backup.timer` → `s3://absolut-cinema-{account}/raw/` y `snapshots/`).
- **RDS:** conectar (red, no IAM).
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

## 4. RDS: PostgreSQL

### Configuración (plan 2)

```
Engine: PostgreSQL 15+
Instance class: db.t4g.micro (dev) / db.t4g.small (prod)
Storage: gp3 20 GB, 3000 IOPS (auto-scaling a 100 GB; ~2.5 GB/año de crecimiento medido)
Backup: 7 días (de inicio), snapshot manual antes de plan 2
Multi-AZ: sí (failover automático a standby en us-east-1b)
Public accessibility: no (solo desde EC2 via SG)
Monitoring: Enhanced Monitoring habilitado
```

### Pasos en AWS Console

1. **RDS → Crear base de datos:**
   - Estándar create
   - Engine: PostgreSQL 15
   - Instance: `db.t4g.micro` (upgrade a `.small` si plan 2 crece)
   - Storage: 20 GB gp3, auto-scaling habilitado
   - VPC: `absolut-cinema`
   - DB Subnet Group: crear `absolut-rds-subnet-group` (AZ-1a, AZ-1b)
   - Public: no
   - VPC Security Group: `absolut-rds`
   - Initial DB: `absolut_cinema`
   - Master user: `postgres` (cambiar en `.env`)
   - Multi-AZ: yes
   - Backup: 7 días
   - Encryption: habilitada

2. **Crear parámetro de grupo (si es necesario):**
   - `rds.force_ssl = 0` (dentro de VPC, SSL opcional)

### Endpoint de conexión
Después de crear, AWS te da:
```
absolut-cinema.c1234567890.us-east-1.rds.amazonaws.com:5432
```

Este va en `deploy/absolut-cinema.env`:
```
DATABASE_URL=postgresql://postgres:PASSWORD@absolut-cinema.c1234567890.us-east-1.rds.amazonaws.com:5432/absolut_cinema
```

---

## 5. EC2: Instancia de la aplicación

### Configuración

```
AMI: Ubuntu 22.04 LTS (Canonical, arm64 t4g compatible)
Instance type: t4g.medium (plan 1) / t4g.small (plan 2)
Storage: EBS gp3 30 GB (plan 1) / 20 GB (plan 2)
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
   - Root: gp3 30 GB (plan 1) o 20 GB (plan 2)
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
#   - Python 3.12 si es plan 2 (Postgres requ psycopg)
#   - Repositorio absolut-cinema en /opt/absolut-cinema
#   - Systemd units en /etc/systemd/system/
#   - Timers: scraper.timer, seats.timer, health.timer, etc.
#   - Caddy (HTTPS + basic auth)
#   - Cloudflare WARP (modo proxy, SOCKS5 :40000) + Privoxy (HTTP :8118) para salir hacia Cinépolis
#   - .env: AC_EGRESS_PROXY=http://127.0.0.1:8118, CINEPOLIS_API_KEY, CINEMEX_CONSUMER_KEY, AC_PG_DSN (si plan 2)
```

---

## 6. S3: Respaldos

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
├─ snapshots/ (snapshots.db diarios)
├─ logs/ (run.log, sample.log, health.log)
└─ rds-snapshots/ (referencias a RDS snapshots, no contenido)
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

## 7. Credenciales y secretos

### Archivo: `deploy/absolut-cinema.env`

Nunca commitear, reemplazar valores:

```bash
# APIs externas (del bundle JS de cada sitio)
CINEPOLIS_API_KEY=lQM6Mkvri1iHksKKCfpAiwGXq0YUZA7Nn6XAXRPr4i13LwXo
CINEMEX_CONSUMER_KEY=XXQha7vz4kdvoMSdixhN
CINEMEX_BASE_URL=https://api.cinemex.com/rest/v2.37.2

# Plan 2: PostgreSQL en RDS (el sync escribe el archivo con este rol)
AC_PG_DSN=postgresql://absolut:PASSWORD_FUERTE@absolut-cinema.c1234567890.us-east-1.rds.amazonaws.com:5432/absolut_cinema
# Acceso al dashboard: rol absolut_app (deploy/postgres/app_role.sql), correo por SES y URL pública para los enlaces
AC_AUTH_PG_DSN=postgresql://absolut_app:OTRA_PASSWORD@absolut-cinema.c1234567890.us-east-1.rds.amazonaws.com:5432/absolut_cinema
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

## 8. Monitoreo y alertas

### CloudWatch

```
Métricas de EC2:
  ├─ CPU Utilization (alertar si > 80%)
  ├─ Memory (cloudwatch-agent, alertar si > 80%)
  └─ Disk (cloudwatch-agent, alertar si > 85%)

Métricas de RDS:
  ├─ CPU Utilization (alertar si > 75%)
  ├─ Database Connections (normal < 10)
  └─ Replication Lag (Multi-AZ standby, ≈0)

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
  - RDS connections > 15
  - health.log indica "problems"
```

---

## 9. Checklist de post-lanzamiento

### Seguridad
- [ ] SSH key guardada localmente en `~/.ssh/absolut-cinema.pem` (permisos 600)
- [ ] Firewall intra-VPC validado (SG EC2 ↔ RDS)
- [ ] IAM policy restringida (solo S3 + logs, sin EC2DescribeInstances)
- [ ] RDS Multi-AZ habilitado
- [ ] Backups automáticos RDS configurados (7 días)

### Operación
- [ ] `deploy/install.sh` ejecutado sin errores
- [ ] Timers arrancados: `systemctl list-timers`
- [ ] Primer snapshot capturado: `ls -la /opt/absolut-cinema/data/snapshots.db`
- [ ] Dashboard accesible en `https://absolut-cinema.ejemplo.com` (Caddy + basic auth)
- [ ] Logs en CloudWatch aparecen

### Base de datos (plan 2)
- [ ] RDS endpoint accesible desde EC2: `psql -h <endpoint> -U postgres -d absolut_cinema`
- [ ] `sync/` job creado y probado (próximo documento)
- [ ] Carga inicial de historia desde SQLite a Postgres

### Respaldos
- [ ] Bucket S3 creado y accesible desde EC2
- [ ] Primer backup en S3: `aws s3 ls s3://absolut-cinema-backup-*/`
- [ ] Ciclo de vida configurado

---

## 10. Migración: plan 1 → plan 2

Cuando esté todo en RDS:

1. **Snapshot de RDS:** AWS lo hace automático (7 días retention).
2. **Migración de datos:** `sync/` job copia historia desde SQLite a Postgres.
3. **Cut-over:** cambiar `analytics/` y dashboard de `snapshots.db` → RDS.
4. **Keepalive:** guardar SQLite en S3 para auditoría.

---

## 11. Costos estimados (plan 2, full)

| Componente | Especificación | Costo/mes USD |
| --- | --- | --- |
| EC2 | t4g.small on-demand | 12.26 |
| EBS | 20 GB gp3 | 1.60 |
| RDS | db.t4g.micro multi-AZ | 22.50 |
| S3 | respaldos + storage | 3.00 |
| NAT Gateway | tráfico + uso | 5.00 |
| CloudWatch | basic logs | 1.00 |
| **Total** | | **~45.36 USD/mes** |

(Precios us-east-1, on-demand. Reserved instances reducen ~25%.)

---

## Referencias

- VPC: https://docs.aws.amazon.com/vpc/
- RDS PostgreSQL: https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/CHAP_PostgreSQL.html
- EC2 IAM: https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/iam-roles-for-amazon-ec2.html
- `deploy/install.sh`: revisa qué paquetes y servicios instala
