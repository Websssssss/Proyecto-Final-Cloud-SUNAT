# Guía de ejecución y pruebas

Instrucciones para levantar la plataforma y reproducir las pruebas que sustentan el informe, por
cuatro vías: **local** (sin contenedores), **Docker Compose**, **Kubernetes** (clúster local con kind)
y **validación estática de la nube** (Terraform / manifiestos).
Todas las órdenes se ejecutan desde la raíz del repositorio.

> **Sobre esta versión de la guía.** Se corrigieron errores de la versión anterior (ver §12) y se
> añadieron las vías de Compose y Kubernetes completas. Las órdenes de Compose y Kubernetes se
> escribieron leyendo los manifiestos, los Dockerfiles y los scripts del proyecto; **no se ejecutaron en
> el equipo donde se redactó la guía** (sin Docker, sin clúster, sin red). Si algún comando difiere en
> su máquina, la sección 12 («Problemas frecuentes») y el estado de verificación del final dicen qué
> revisar primero.

---

## 1. Requisitos

| Vía | Necesita |
|---|---|
| Local (la más rápida para la sustentación) | Python 3.11 o superior (el proyecto se construye con 3.12) |
| Docker Compose | Docker Engine 24+ con el plugin `docker compose` v2, `openssl` y `sha256sum` (para los respaldos) |
| Kubernetes local | Lo anterior, más [`kind`](https://kind.sigs.k8s.io) y `kubectl` |
| Validación de la nube | `terraform` 1.x (solo para `validate`; no hace falta cuenta de nube) |
| Prueba de carga (opcional) | [k6](https://k6.io) |

**Recursos de la máquina.** Compose corre 12 contenedores y cabe en 4 GB. Kubernetes en su configuración
completa programa unos 28 pods (≈ 4 CPU y 4,5 GiB de *requests*): asigne **4 CPU y 8 GB** a Docker Desktop, o
use el «modo ligero» de §6.6, que reduce todo a una réplica.

**Sistema operativo.** Los scripts `.sh` usan `sha256sum`, `date -r` y `pkill` de GNU/Linux. Use Linux,
macOS con las utilidades GNU (`brew install coreutils`) o **WSL2** en Windows. En Windows nativo, ejecute los
scripts desde Git Bash o WSL, no desde PowerShell.

---

## 2. Preparación común

```bash
python3 -m venv .venv && source .venv/bin/activate    # Windows (PowerShell): .venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-dev.txt
```

Las dependencias de Python sirven para `pytest`, `scripts/e2e.py` y `scripts/totp.py`, incluso si la
plataforma corre en contenedores.

### 2.1 Credenciales de demostración

| Dato | Valor |
|---|---|
| RUC | `10123456789` |
| Usuario | `PSICOLOGA1` |
| Clave | `Demo#2026` |
| Código de verificación (TOTP) | el que imprima `python scripts/totp.py` |

El secreto TOTP de la demostración es fijo (`JBSWY3DPEHPK3PXP`), por lo que `totp.py` funciona igual con
la plataforma local, en Compose o en Kubernetes. El código cambia cada 30 segundos: genérelo justo antes
de escribirlo. El usuario demo solo existe si la capa de datos arranca con `SEED_DEMO=1`
(las secciones siguientes ya lo configuran).

### 2.2 Secretos para contenedores y Kubernetes

La clave de cifrado de campo (`KMS_KEYS`) **no tiene valor por defecto** en Compose ni en Kubernetes: si
queda vacía, Compose se niega a arrancar. Genere una (32 bytes en base64 urlsafe; no requiere paquetes extra):

```bash
python3 -c "import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
```

> Guarde esa clave. Si la pierde o la cambia, los documentos ya cifrados en la base dejan de poder leerse
> (`No se pudo descifrar: la clave no está disponible`). Para rotarla se antepone una clave nueva separada
> por coma: la primera cifra y todas descifran.

---

## 3. Vía A — Local, sin contenedores

```bash
bash scripts/run_local.sh
```

El guion arranca la capa de datos privada (puerto 8100), los nueve microservicios (8101-8109) y una pasarela
de desarrollo que hace de portal. Cuando termine, abra **http://localhost:8080**. Usa SQLite y genera una
`KMS_KEYS` efímera en cada ejecución (borra `local.db` al empezar). Para detenerlo: `Ctrl+C`.

Qué **no** ejercita esta vía (solo existe en contenedores y Kubernetes): nginx con límites de tasa,
encabezados CSP/HSTS, PostgreSQL, redes aisladas, NetworkPolicies, HPA.

Verificar la bitácora de auditoría (la clave interna de esta vía es `local-key`):

```bash
curl -H "X-Internal-Key: local-key" http://localhost:8100/internal/auditoria/verificar
```

Devuelve `{"integra": true, "registros": N}`. Si alguien altera una fila de la bitácora, `integra` pasa a
`false` e indica el primer registro roto (`primer_error`).

---

## 4. Pruebas automatizadas

```bash
python -m pytest -q
```

Resultado esperado: **28 pruebas correctas** (7 en `test_flujos.py` y 21 en `test_tramites.py`). No requieren
que la plataforma esté levantada: cada prueba monta los servicios en memoria contra una base temporal.

| Archivo | Qué comprueba |
|---|---|
| `tests/test_flujos.py` | Los flujos completos de cada trámite, paso por paso |
| `tests/test_tramites.py` | Reglas de cálculo, seguridad, cifrado, auditoría y concurrencia |

Para ver el nombre de cada prueba: `python -m pytest -v`.

### 4.1 El flujo de referencia: emitir un recibo por honorarios

Recorre las cinco etapas del caso:

```bash
python -m pytest tests/test_flujos.py::test_flujo_emitir_recibo_por_honorarios -v
```

| Paso | Qué verifica la prueba |
|---|---|
| 1. Identidad | Sin credencial, o con una falsificada, la emisión responde 401 |
| 2. Borde | Un RUC mal formado o un monto negativo se rechazan con 422 antes de llegar al negocio |
| 3. Nube pública | El microservicio calcula la retención del 8 % y el neto, sin tocar la base de datos |
| 4. Nube privada | La constancia se archiva en la gestión documental, se descarga como PDF y en la base figura cifrada (prefijo `v2$`, sin el texto en claro) |
| 5. Notificación | Queda una confirmación en la bandeja del contribuyente; el despachador la entrega una sola vez |
| Transversal | Los tres recursos quedan en la bitácora y la cadena de hashes sigue enlazada |

Los demás trámites siguen el mismo patrón y tienen su propia prueba: pago a cuenta, declaración anual,
fraccionamiento y cambio de régimen.

---

## 5. Vía B — Docker Compose

Simula la nube híbrida con tres redes: `publica` (portal y microservicios), `enlace` (único puente) y
`privada` (PostgreSQL, red `internal`, sin salida al exterior). Los microservicios no tienen ruta hacia
PostgreSQL; solo hablan con `datos-privados`.

### 5.1 Configurar y levantar

```bash
cp .env.example .env
```

Edite `.env` y pegue la clave generada en §2.2 como valor de `KMS_KEYS=`. (En Linux puede hacerlo de una
vez: `sed -i "s|^KMS_KEYS=.*|KMS_KEYS=$(python3 -c 'import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())')|" .env`.
En macOS use `sed -i ''`.) Deje `SEED_DEMO=1`: sin él no existe el usuario demo. Las contraseñas de ejemplo
sirven para desarrollo; cámbielas si va a exponer el equipo a una red.

```bash
docker compose config -q        # valida .env: si falta KMS_KEYS u otra variable, falla aquí con un mensaje claro
docker compose up --build -d
docker compose ps               # esperar ~30-60 s hasta ver «healthy» en los servicios
```

Deben quedar **12 contenedores**: `portal`, `auth`, `ruc`, `rhe`, `declaraciones`, `alertas`,
`fraccionamiento`, `pagos`, `documentos`, `simulador`, `datos-privados` y `postgres`. Solo `portal` publica un
puerto (8080) en su equipo. Abra **http://localhost:8080** e ingrese con las credenciales de §2.1.

Si algo no arranca: `docker compose logs datos-privados` (es el primero del que dependen los demás).

### 5.2 Prueba de humo extremo a extremo

```bash
python scripts/e2e.py            # contra http://localhost:8080
```

Ejecuta **19 comprobaciones** por HTTP sobre los servicios reales: página y encabezado CSP, calendario
público, simulador de multas, rechazo sin token, ingreso con segundo factor, ficha RUC, emisión de recibo
con retención del 8 %, cálculo de renta, fraccionamiento, pago a cuenta, archivo y descarga de la constancia
en PDF, adjuntar un sustento, rechazo de un archivo que no es PDF/PNG/JPG, y notificaciones. Termina con
`Resultado: TODO CORRECTO`.

> Cada ejecución consume cupo del límite de ingreso de nginx (10 intentos/min por IP). Si la repite varias
> veces seguidas obtendrá `429`; espere un minuto.

### 5.3 Pruebas de seguridad y arquitectura

| Qué se demuestra | Orden | Resultado esperado |
|---|---|---|
| Datos cifrados en la base | `docker compose exec postgres psql -U tramites -d tramites -c "SELECT tipo, left(payload,24) FROM documentos LIMIT 5;"` | Cada `payload` empieza por `v2$` y no se lee texto en claro |
| Los microservicios no llegan a la base | `docker compose exec auth python -c "import socket;socket.create_connection(('postgres',5432),3)"` | **Falla** (no resuelve el nombre `postgres` desde la red pública) |
| La red privada no sale a Internet | `docker compose exec postgres wget -T 3 -qO- http://example.com` | **Falla** o agota el tiempo |
| Solo el portal está expuesto | `docker compose ps` | Solo `portal` muestra `0.0.0.0:8080->8080` |
| Contenedores sin privilegios | `docker compose exec auth id` | `uid=10001`, no root |
| Sistema de archivos de solo lectura | `docker compose exec auth sh -c "touch /app/x"` | `Read-only file system` |
| Encabezados de seguridad | `curl -sI http://localhost:8080 \| grep -iE "content-security\|x-frame\|strict-transport"` | Aparecen los tres |
| Límite de tasa en el ingreso | Ver recuadro abajo | Primero rechazos de credenciales y luego `429` |
| Bitácora íntegra | Ver recuadro abajo | `{"integra": true, "registros": N}` |

En Compose los microservicios no publican puertos, así que la auditoría se consulta desde dentro del contenedor
(la clave interna es la de su `.env`):

```bash
docker compose exec datos-privados python -c "import os,urllib.request as u;print(u.urlopen(u.Request('http://127.0.0.1:8000/internal/auditoria/verificar',headers={'X-Internal-Key':os.environ['INTERNAL_API_KEY']})).read().decode())"
```

Límite de tasa (use un RUC inventado para no bloquear la cuenta demo, que también tiene bloqueo por intentos):

```bash
for i in $(seq 1 15); do curl -s -o /dev/null -w "%{http_code} " -X POST http://localhost:8080/api/auth/login \
  -H 'Content-Type: application/json' -d '{"ruc":"10999999999","usuario":"X","clave":"x"}'; done; echo
```

Tras esta prueba espere un minuto antes de volver a ingresar.

### 5.4 Despachador de alertas

En Kubernetes lo ejecuta un CronJob; en Compose se lanza a mano (tras haber corrido `e2e.py`, que deja
confirmaciones pendientes):

```bash
docker compose exec alertas python -m tramites.alertas.dispatcher
```

Imprime eventos JSON `alerta_enviada` y `notificacion_entregada`. Una segunda ejecución no repite las
notificaciones ya entregadas.

### 5.5 Resiliencia: caída de la capa de datos

```bash
docker compose stop datos-privados
curl -s -o /dev/null -w "simulador: %{http_code}\n" -X POST localhost:8080/api/simulador/multa \
  -H 'Content-Type: application/json' -d '{"tributo_omitido":1000,"dias_retraso":30}'
curl -s -o /dev/null -w "ingreso:   %{http_code}\n" -X POST localhost:8080/api/auth/login \
  -H 'Content-Type: application/json' -d '{"ruc":"10123456789","usuario":"PSICOLOGA1","clave":"Demo#2026"}'
docker compose start datos-privados
```

El simulador (que no usa datos personales) sigue respondiendo `200`; el ingreso falla con un error 5xx
mientras la capa de datos está caída. Al reiniciarla, todo vuelve sin intervención.

### 5.6 Simulacro de recuperación ante desastres

Requiere la plataforma en marcha (usa PostgreSQL) y la frase de respaldo **exportada en el entorno** (no basta
con ponerla en `.env`):

```bash
export BACKUP_PASSPHRASE='una-frase-larga-y-secreta'
bash scripts/dr_test.sh
```

Hace una prueba de humo, genera un respaldo cifrado en `backups/`, destruye la base y su volumen, levanta un
PostgreSQL nuevo, restaura, vuelve a correr la prueba de humo y muestra el **RTO medido**, que debe quedar muy por
debajo del objetivo de 7 200 s (2 h) de `docs/DRP.md`. El RPO depende del último respaldo (objetivo 15 min).
Respaldo y restauración sueltos: `scripts/backup.sh` y `scripts/restore.sh backups/tramites_<fecha>.sql.enc`.

### 5.7 Observabilidad (opcional)

```bash
docker compose --profile observabilidad up -d prometheus      # http://localhost:9090/targets
```

Limitaciones actuales: el `prometheus.yml` no incluye los servicios `pagos` ni `documentos`, y el archivo de
reglas `monitoring/alertas.rules.yml` no está montado en el contenedor, por lo que las alertas no se cargan. Para
verlas, añada al servicio `prometheus` del compose
`- ./monitoring/alertas.rules.yml:/etc/prometheus/alertas.rules.yml:ro` y los dos destinos
(`pagos:8000`, `documentos:8000`) en `monitoring/prometheus.yml`.

### 5.8 Prueba de carga

```bash
k6 run --stage 30s:10,1m:10,10s:0 tests/load/pico_vencimiento.js
```

> **Cuidado con el escenario completo.** El script original sube a 1 000 usuarios virtuales desde una sola
> máquina, y el límite de tasa de nginx (30 solicitudes/s por IP) los rechazará con `429`; el umbral
> `http_req_failed < 1 %` fallará aunque el sistema funcione bien: es el limitador haciendo su trabajo. La
> versión de arriba (10 usuarios) queda dentro del límite y sirve para comprobar que el camino funciona. Medir
> el escalado real exige varias IP de origen o subir temporalmente los límites de `portal/nginx.conf`.

### 5.9 Apagar

```bash
docker compose down            # conserva los datos (volumen pgdata)
docker compose down -v         # además borra la base
```

---

## 6. Vía C — Kubernetes (clúster local con kind)

Reproduce las **dos nubes** como dos namespaces de un mismo clúster: `tramites-datos` (nube privada: PostgreSQL
y la capa de datos) y `tramites` (nube pública: portal y nueve microservicios).

### 6.1 Qué hay que adaptar y por qué

Los manifiestos de `k8s/` están pensados para el despliegue real. Aplicados tal cual con
`kubectl apply -k` en un clúster local **no arrancan**. Esta tabla resume lo que se cambia aquí:

| Elemento del manifiesto | Problema en local | Qué se hace |
|---|---|---|
| Imágenes `REGISTRO/tramites-*` (en `kustomization.yaml`) | `REGISTRO` en mayúsculas no es un nombre de imagen válido y no hay registro | Se construyen imágenes `tramites/<servicio>:latest` (el nombre que traen los YAML) y se cargan en kind; se aplican los archivos con `-f`, sin kustomize |
| Secretos con valor `REEMPLAZAR` | Los servicios arrancarían con claves falsas y `KMS_KEYS` inválida | Se crean con `kubectl create secret` con valores generados |
| `datos-privados` apunta a la IP `10.20.0.10` (`20-enlace-datos-privados.yaml`) | Esa IP es del centro de datos real | Se crea un Service `ExternalName` hacia el namespace `tramites-datos` |
| NetworkPolicies con `ipBlock` `10.10.0.0/16` y `10.20.0.0/24` | En un solo clúster el tráfico entre namespaces viene de IP de pods, y que se apliquen depende del CNI | No se aplican (ver §6.8) |
| Ingress con anotaciones de AWS ALB y WAF | No hay controlador ALB en kind | No se aplica; se accede con `port-forward` |
| `datos-privados` sin `SEED_DEMO` | No existiría el usuario demo | Se añade la variable con `kubectl set env` |
| 22+ réplicas y HPA con mínimos de 2 a 3 | Excede un portátil | «Modo ligero» opcional (§6.6) |

### 6.2 Crear el clúster y las imágenes

```bash
kind create cluster --name tramites
kubectl config use-context kind-tramites

SERVICIOS="auth ruc rhe declaraciones alertas simulador fraccionamiento pagos documentos datos"
for s in $SERVICIOS; do
  docker build -f docker/Dockerfile.service --build-arg SERVICE=$s -t tramites/$s:latest .
done
docker build -f docker/Dockerfile.portal -t tramites/portal:latest .

kind load docker-image --name tramites \
  $(for s in $SERVICIOS portal; do echo tramites/$s:latest; done)
```

(Con minikube: `minikube image load tramites/<n>:latest` por cada imagen. Con el Kubernetes de Docker
Desktop no hace falta cargar nada: ve las imágenes locales.)

### 6.3 Generar los secretos

Todos en la **misma terminal**, porque se usan en los pasos siguientes:

```bash
export KMS_KEYS=$(python3 -c "import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())")
export INTERNAL_API_KEY=$(python3 -c "import secrets;print(secrets.token_urlsafe(32))")
export JWT_SECRET=$(python3 -c "import secrets;print(secrets.token_urlsafe(48))")
export POSTGRES_PASSWORD=$(python3 -c "import secrets;print(secrets.token_urlsafe(24))")
export BACKUP_PASSPHRASE=$(python3 -c "import secrets;print(secrets.token_urlsafe(24))")
```

`INTERNAL_API_KEY` debe ser **idéntica** en ambas nubes: es la credencial con la que los microservicios le
hablan a la capa de datos.

### 6.4 Nube privada (namespace `tramites-datos`)

```bash
kubectl apply -f k8s/onprem/00-namespace.yaml

kubectl -n tramites-datos create secret generic datos-secretos \
  --from-literal=POSTGRES_PASSWORD="$POSTGRES_PASSWORD" \
  --from-literal=INTERNAL_API_KEY="$INTERNAL_API_KEY" \
  --from-literal=JWT_SECRET="$JWT_SECRET" \
  --from-literal=KMS_KEYS="$KMS_KEYS" \
  --from-literal=BACKUP_PASSPHRASE="$BACKUP_PASSPHRASE"

kubectl apply -f k8s/onprem/20-postgres.yaml
kubectl -n tramites-datos rollout status statefulset/postgres --timeout=240s

kubectl apply -f k8s/onprem/30-datos-privados.yaml
```

Active el usuario demo. Se hace con **una sola réplica** para que dos réplicas no siembren a la vez, y después
se restablece la segunda:

```bash
kubectl -n tramites-datos scale deploy/datos-privados --replicas=1
kubectl -n tramites-datos set env deploy/datos-privados SEED_DEMO=1
kubectl -n tramites-datos rollout status deploy/datos-privados --timeout=240s
kubectl -n tramites-datos scale deploy/datos-privados --replicas=2
```

El Service `datos-privados` es de tipo `LoadBalancer` (pensado para el balanceador interno del centro de datos);
en kind su `EXTERNAL-IP` queda en `<pending>`, y es normal: el acceso interno por ClusterIP funciona igual.

### 6.5 Nube pública (namespace `tramites`)

```bash
kubectl apply -f k8s/publica/00-namespace.yaml
kubectl apply -f k8s/publica/10-config-secretos.yaml           # crea el ConfigMap y un Secret de plantilla
kubectl -n tramites delete secret tramites-secretos            # se descarta la plantilla...
kubectl -n tramites create secret generic tramites-secretos \
  --from-literal=INTERNAL_API_KEY="$INTERNAL_API_KEY" \
  --from-literal=JWT_SECRET="$JWT_SECRET"                      # ...y se crea el real

# Enlace híbrido simulado: «datos-privados» resuelve al namespace de la nube privada
kubectl -n tramites create service externalname datos-privados \
  --external-name datos-privados.tramites-datos.svc.cluster.local --tcp=8000:8000

for f in k8s/publica/30-*.yaml k8s/publica/40-portal.yaml k8s/publica/70-cronjob-alertas.yaml; do
  kubectl apply -f "$f"
done
kubectl -n tramites wait --for=condition=available deploy --all --timeout=300s
kubectl get pods -A
```

(No se aplican `20-enlace-datos-privados.yaml`, `50-ingress.yaml` ni `60-networkpolicies.yaml`: ver §6.1.)
Si algún pod queda en `Pending`, es falta de recursos: use el modo ligero de §6.6.

### 6.6 Modo ligero (recomendado en un portátil)

Elimina los autoescaladores y deja una réplica por servicio. Es la configuración con la que conviene hacer las
pruebas funcionales; los autoescaladores se reponen en §6.9.

```bash
kubectl -n tramites delete hpa --all
kubectl -n tramites scale deploy --all --replicas=1
```

### 6.7 Acceder al portal y probar

En una terminal aparte (queda en primer plano):

```bash
kubectl -n tramites port-forward svc/portal 8080:80
```

Abra **http://localhost:8080** y ejecute la misma prueba de humo de Compose:

```bash
python scripts/e2e.py http://localhost:8080        # esperado: TODO CORRECTO (19 comprobaciones)
```

Comprobaciones propias de Kubernetes:

```bash
# Datos cifrados en PostgreSQL
kubectl -n tramites-datos exec postgres-0 -- psql -U tramites -d tramites -c "SELECT tipo, left(payload,24) FROM documentos LIMIT 5;"

# Bitácora íntegra
kubectl -n tramites-datos exec deploy/datos-privados -- python -c "import os,urllib.request as u;print(u.urlopen(u.Request('http://127.0.0.1:8000/internal/auditoria/verificar',headers={'X-Internal-Key':os.environ['INTERNAL_API_KEY']})).read().decode())"

# Despachador de alertas (el CronJob corre cada 15 min; aquí se fuerza una ejecución)
kubectl -n tramites create job --from=cronjob/alertas-despachador prueba-despacho
kubectl -n tramites logs job/prueba-despacho

# Contenedores sin privilegios y con Pod Security «restricted»
kubectl get ns tramites tramites-datos --show-labels
kubectl -n tramites exec deploy/auth -- id
```

### 6.8 Aislamiento de red (NetworkPolicies)

Los manifiestos `k8s/publica/60-networkpolicies.yaml` y `k8s/onprem/40-networkpolicies.yaml` implementan «denegar
todo» y permisos mínimos (portal → servicios → capa de datos → PostgreSQL), pero están escritos con los rangos de
red del despliegue real (VPC `10.10.0.0/16`, centro de datos `10.20.0.0/24`). **No se pueden probar tal cual en un
clúster único**, y además requieren un CNI que las aplique (Calico o Cilium; con el CNI por defecto de algunos
clústeres locales se aceptan pero no se hacen cumplir). Para el informe, el aislamiento de red se demuestra con
Compose (§5.3, redes `privada`/`enlace`/`publica`) y la revisión de esos manifiestos. Si necesita demostrarlas en
Kubernetes, hay que adaptar las dos reglas con `ipBlock` a selectores de namespace y usar kind con Calico.

### 6.9 Pruebas de resiliencia y de operación

Mantenga el `port-forward` abierto. En cada prueba, una segunda terminal observa el servicio con un bucle.

**a) Actualización sin caída (`maxUnavailable: 0`)**

```bash
# Terminal 2: debe imprimir solo 200
while true; do curl -s -o /dev/null -w "%{http_code}\n" localhost:8080/api/alertas/calendario/9; sleep 0.3; done
# Terminal 1:
kubectl -n tramites rollout restart deploy/alertas
kubectl -n tramites rollout status deploy/alertas
```

**b) Reversión**

```bash
kubectl -n tramites rollout history deploy/alertas
kubectl -n tramites rollout undo deploy/alertas
```

**c) Autorreparación de un microservicio** (con dos réplicas para que no haya hueco)

```bash
kubectl -n tramites scale deploy/rhe --replicas=2
kubectl -n tramites rollout status deploy/rhe
# Terminal 2: responde 401 constante (sin token, pero demuestra que el servicio contesta)
while true; do curl -s -o /dev/null -w "%{http_code}\n" localhost:8080/api/rhe; sleep 0.3; done
# Terminal 1:
kubectl -n tramites delete pod "$(kubectl -n tramites get pod -l app=rhe -o name | head -1)"
```

Mientras Kubernetes recrea el pod, la otra réplica atiende; puede aparecer algún `502` aislado.

**d) Caída de la capa de datos: los servicios públicos independientes siguen vivos**

```bash
kubectl -n tramites-datos scale deploy/datos-privados --replicas=0
curl -s -o /dev/null -w "simulador: %{http_code}\n" -X POST localhost:8080/api/simulador/multa \
  -H 'Content-Type: application/json' -d '{"tributo_omitido":1000,"dias_retraso":30}'      # 200
curl -s -o /dev/null -w "ingreso:   %{http_code}\n" -X POST localhost:8080/api/auth/login \
  -H 'Content-Type: application/json' -d '{"ruc":"10123456789","usuario":"PSICOLOGA1","clave":"Demo#2026"}'   # 5xx
kubectl -n tramites-datos scale deploy/datos-privados --replicas=2
```

**e) Pérdida del pod de PostgreSQL: los datos persisten (volumen)**

```bash
kubectl -n tramites-datos delete pod postgres-0
kubectl -n tramites-datos rollout status statefulset/postgres
python scripts/e2e.py http://localhost:8080        # el usuario y los recibos previos siguen ahí
```

**f) Respaldo cifrado**

El CronJob de respaldo vuelca y cifra la base en un volumen y luego sube la copia a S3 con KMS. Fuera de AWS no
hay bucket, así que solo se puede comprobar la primera mitad (el volcado y cifrado):

```bash
kubectl apply -f k8s/onprem/50-cronjob-respaldo.yaml
kubectl -n tramites-datos create job --from=cronjob/respaldo-postgres prueba-respaldo
kubectl -n tramites-datos get pods -l job-name=prueba-respaldo -w
kubectl -n tramites-datos describe pod -l job-name=prueba-respaldo | grep -A6 "volcado:"
kubectl -n tramites-datos patch cronjob respaldo-postgres -p '{"spec":{"suspend":true}}'   # evita fallos cada 15 min
```

Esperado: el *initContainer* `volcado` termina con `Completed` (exit 0) y el contenedor `subida` falla, porque
`s3://REEMPLAZAR_BUCKET_RESPALDOS` no existe. La restauración completa se prueba con Compose (§5.6).

**g) Autoescalado (HPA)**

Requiere el modo completo (sin §6.6) y *metrics-server*. En kind:

```bash
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
kubectl -n kube-system patch deploy metrics-server --type=json \
  -p '[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'
kubectl -n tramites apply -f k8s/publica/30-simulador.yaml          # restablece el HPA si lo había borrado
kubectl -n tramites get hpa -w
```

Genere carga con k6 como en §5.8 (aplican las mismas salvedades del limitador de tasa). Con la carga de un solo
equipo es probable que el HPA casi no escale; para ver réplicas subir, use varias máquinas o relaje los límites de
`portal/nginx.conf`.

### 6.10 Limpiar

```bash
kind delete cluster --name tramites
```

---

## 7. Vía D — Validación de la nube real (sin desplegar)

No requiere cuenta de nube ni clúster:

```bash
# Los manifiestos compilan con kustomize (incluido en kubectl)
kubectl kustomize k8s/publica > /dev/null && kubectl kustomize k8s/onprem > /dev/null && echo "kustomize OK"

# Los YAML coinciden con el generador (mismo control que el CI). Requiere pyyaml y un repositorio git
python scripts/gen_k8s.py && git diff --exit-code k8s

# Terraform: sintaxis y coherencia (descarga proveedores; no necesita credenciales)
cd infra/terraform && terraform init -backend=false && terraform validate && terraform fmt -check
```

Los manifiestos se generan con `python scripts/gen_k8s.py`; no se editan a mano.

Para un despliegue real hay que reemplazar, como mínimo: el registro (`REGISTRO` en los `kustomization.yaml`), los
secretos (`REEMPLAZAR` en `10-config-secretos.yaml` y `10-secretos.yaml`, que en producción vienen de un gestor de
secretos), la IP `10.20.0.10` del centro de datos, los ARN del WAF, del certificado y del rol de respaldo, y el
dominio del Ingress. Después: `kubectl apply -k k8s/onprem` en el clúster del centro de datos y
`kubectl apply -k k8s/publica` en el de la nube pública. `infra/terraform/README.md` aclara que `terraform
plan/apply` **no se ha ejecutado** y genera costos continuos (NAT, nodos EKS, VPN, WAF).

---

## 8. Matriz para la sustentación

| Requisito del caso | Cómo se demuestra | Dónde |
|---|---|---|
| Flujo de trámite de cinco etapas | `pytest tests/test_flujos.py::test_flujo_emitir_recibo_por_honorarios -v` | §4.1 |
| Identidad y segundo factor | Ingreso con TOTP en el portal; `401` sin token | §2.1, §5.2 |
| Cifrado de datos sensibles | `SELECT … left(payload,24)` muestra `v2$…` | §5.3, §6.7 |
| Integridad de la auditoría | `/internal/auditoria/verificar` → `integra: true` | §3, §5.3, §6.7 |
| Aislamiento nube pública / privada | La conexión a `postgres` desde `auth` falla | §5.3 |
| Borde y límites de tasa | `429` en ingreso; encabezados CSP/HSTS | §5.3 |
| Contenedores endurecidos | `uid=10001`, solo lectura, sin capacidades | §5.3, §6.7 |
| Actualización sin caída y reversión | `rollout restart` con bucle de `curl`, `rollout undo` | §6.9 a-b |
| Autorreparación y persistencia | Borrar pods de servicio y de PostgreSQL | §6.9 c, e |
| Degradación controlada | Caída de la capa de datos: el simulador sigue | §5.5, §6.9 d |
| Continuidad y DRP (RTO/RPO) | `dr_test.sh` mide el RTO | §5.6 |
| Autoescalado en el pico | HPA + k6 | §5.8, §6.9 g |
| Nube pública real (red, EKS, KMS, WAF) | Revisión estática y `terraform validate` | §7 |

---

## 9. Qué mirar en la interfaz

| Pantalla | Qué demuestra |
|---|---|
| Inicio | Indicadores del contribuyente y próximos vencimientos |
| Recibos por honorarios | Emisión con cálculo automático de la retención y resumen del ejercicio |
| Pagos a cuenta | Determinación del importe a partir de los recibos del periodo |
| Mi expediente | Constancias en PDF de cada trámite y adjuntado de sustentos |
| Mis alertas | Calendario, suscripción a avisos y bandeja de notificaciones |

---

## 10. Estado de verificación de esta guía

| Parte | Estado |
|---|---|
| Contenido de manifiestos, Dockerfiles, `docker-compose.yml`, scripts y código | Leído completo para redactar la guía |
| Valores citados (credenciales, 28 pruebas, 19 comprobaciones, claves, puertos, rutas) | Contrastados con el código |
| `pytest`, `run_local.sh`, `e2e.py` | **No ejecutados al redactar** (el equipo no tenía las dependencias ni red) |
| Compose (§5) y Kubernetes (§6) | **No ejecutados**: sin Docker ni clúster. Los comandos de §6 usan solo operaciones estándar de `kubectl` y los YAML tal como están en el repositorio |
| Terraform | `terraform plan/apply` no ejecutado (lo indica su propio README) |

Antes de presentar el resultado como probado, ejecute la guía una vez de principio a fin y anote cualquier
diferencia.

---

## 11. Estructura de pruebas y archivos útiles

| Archivo | Para qué |
|---|---|
| `scripts/run_local.sh` | Plataforma completa sin contenedores |
| `scripts/e2e.py` | Prueba de humo (19 comprobaciones) contra cualquier URL |
| `scripts/totp.py` | Código del segundo factor del usuario demo |
| `scripts/backup.sh`, `restore.sh`, `dr_test.sh` | Respaldo, restauración y simulacro de desastre (Compose) |
| `scripts/gen_k8s.py` | Regenera `k8s/` |
| `tests/load/pico_vencimiento.js` | Carga del día de vencimiento (k6) |
| `docs/DRP.md`, `docs/SEGURIDAD.md` | Objetivos RTO/RPO y modelo de seguridad |

---

## 12. Problemas frecuentes

| Síntoma | Causa y solución |
|---|---|
| `docker compose` falla con `defina KMS_KEYS` (o `POSTGRES_PASSWORD`, etc.) | `.env` incompleto. `.env.example` trae `KMS_KEYS=` vacío: genere la clave de §2.2 |
| `Credenciales inválidas` al ingresar | El código del segundo factor caducó (dura 30 s). Genérelo de nuevo con `python scripts/totp.py` |
| `429` al ingresar o al repetir `e2e.py` | Límite de nginx (10 intentos/min por IP) o bloqueo temporal de la cuenta tras intentos fallidos. Espere un minuto |
| El usuario demo no existe | La capa de datos arrancó sin `SEED_DEMO=1` (Compose: revise `.env`; Kubernetes: §6.4) |
| `No se pudo descifrar: la clave no está disponible` | `KMS_KEYS` distinta de la que cifró los datos. Restaure la clave original o borre el volumen y reinicie |
| El portal responde pero los trámites fallan | La capa de datos privada no arrancó. Local: puerto 8100. Compose: `docker compose logs datos-privados`. Kubernetes: `kubectl -n tramites-datos logs deploy/datos-privados` |
| `dr_test.sh`: `Defina BACKUP_PASSPHRASE` | La variable debe estar exportada en la terminal (`export BACKUP_PASSPHRASE=…`) |
| `sha256sum: command not found` o `date: illegal option -r` (macOS) | Faltan utilidades GNU: `brew install coreutils` o use WSL |
| `Address already in use` | Quedó una ejecución anterior. Cierre con `pkill -f "uvicorn tramites"` (local) o `docker compose down` |
| `ModuleNotFoundError` | Falta activar el entorno virtual o instalar `requirements.txt` |
| La descarga del PDF no inicia | El navegador bloqueó la ventana emergente. Permita descargas del sitio |
| Kubernetes: `ErrImagePull` / `ImagePullBackOff` | La imagen no está cargada en el clúster: repita `kind load docker-image …` (§6.2) y reinicie con `kubectl -n <ns> rollout restart deploy/<nombre>` |
| Kubernetes: pods en `Pending` | Falta de CPU/memoria. Aumente los recursos de Docker o use el modo ligero (§6.6) |
| Kubernetes: `CrashLoopBackOff` en `datos-privados` | `KMS_KEYS` inválida o PostgreSQL aún sin listo. `kubectl -n tramites-datos logs deploy/datos-privados` |
| Kubernetes: el portal no abre | Falta el `port-forward` de §6.7, o se cerró esa terminal |
| Prometheus sin alertas ni `pagos`/`documentos` | Limitación conocida del compose (ver §5.7) |

### Cambios respecto de la versión anterior de la guía

- `.env.example` deja `KMS_KEYS` vacío y Compose lo exige: se añadió la generación de la clave (la guía decía
  solo «copiar y revisar»).
- La verificación de auditoría usaba la clave `clave-local-insegura`; la de `run_local.sh` es `local-key`. En
  Compose y Kubernetes se consulta dentro del contenedor.
- La prueba de humo tiene **19** comprobaciones, no veintiuna.
- `dr_test.sh` exige `BACKUP_PASSPHRASE` exportada; no estaba mencionado.
- `kubectl apply -k` no funciona en un clúster local por los marcadores `REGISTRO` / `REEMPLAZAR`, la IP fija del
  enlace y el Ingress de AWS: ahora hay un procedimiento completo y comprobable (§6).
- Se añadieron requisitos de sistema, pruebas de seguridad, resiliencia y carga, y la salvedad del limitador de
  tasa sobre la prueba k6.
